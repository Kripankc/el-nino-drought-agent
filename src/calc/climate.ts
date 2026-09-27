import { Day, dayOfYear, daysInMonth, ymd } from "../lib/dates";
import { CropParams, Season, effectiveRain, kcOnDay, stagePlan } from "./season";
import { finite, mean, percentileRank, quantile } from "./stats";

export type Vars = "precip" | "tmax" | "tmin" | "et0" | "rh" | "sm";

export interface Daily {
  day: Day[];
  precip: (number | null)[];
  tmax: (number | null)[];
  tmin: (number | null)[];
  et0: (number | null)[];
  rh: (number | null)[];
  sm: (number | null)[];
}

export interface Band { p10: number; p50: number; p90: number }

export const CLIM_START = 1991;
export const CLIM_END = 2020;

/** Index lookup: day -> row. */
export function indexOf(d: Daily): Map<Day, number> {
  const m = new Map<Day, number>();
  d.day.forEach((day, i) => m.set(day, i));
  return m;
}

export function slice(d: Daily, from: Day, to: Day): Daily {
  const idx = d.day.map((day, i) => (day >= from && day <= to ? i : -1)).filter((i) => i >= 0);
  const pick = <T,>(a: T[]) => idx.map((i) => a[i]);
  return {
    day: pick(d.day), precip: pick(d.precip), tmax: pick(d.tmax), tmin: pick(d.tmin),
    et0: pick(d.et0), rh: pick(d.rh), sm: pick(d.sm),
  };
}

/**
 * Day-of-year climatology band (10th/50th/90th percentile) from a centred
 * +/- `halfWindow` day window pooled over the climatology years.
 */
export function doyBands(clim: Daily, v: Exclude<Vars, "precip">, halfWindow = 7): (Band | null)[] {
  const bins: number[][] = Array.from({ length: 367 }, () => []);
  clim.day.forEach((day, i) => {
    const x = clim[v][i];
    if (x == null || !Number.isFinite(x)) return;
    const y = ymd(day).y;
    if (y < CLIM_START || y > CLIM_END) return;
    const d = dayOfYear(day);
    for (let k = -halfWindow; k <= halfWindow; k++) {
      let dd = d + k;
      if (dd < 1) dd += 366;
      if (dd > 366) dd -= 366;
      bins[dd].push(x);
    }
  });
  return bins.map((b, doy) =>
    doy === 0 || b.length < 30 ? null
      : { p10: quantile(b, 0.1), p50: quantile(b, 0.5), p90: quantile(b, 0.9) });
}

/** Cumulative sum of a variable from season.plant over `n` days (null where data missing). */
export function cumulative(d: Daily, v: Vars, start: Day, n: number): (number | null)[] {
  const ix = indexOf(d);
  const out: (number | null)[] = [];
  let acc = 0;
  let broken = false;
  for (let k = 0; k < n; k++) {
    const i = ix.get(start + k);
    const x = i === undefined ? null : d[v][i];
    if (x == null || broken) { broken = true; out.push(null); continue; }
    acc += x;
    out.push(acc);
  }
  return out;
}

/** Climatological band of cumulative rainfall since planting, per day of season. */
export function cumulativeRainBand(
  clim: Daily, seasonFor: (y: number) => Season, length: number,
): { bands: Band[]; years: number[]; curves: number[][] } {
  const curves: number[][] = [];
  const years: number[] = [];
  for (let y = CLIM_START - 1; y <= CLIM_END; y++) {
    const s = seasonFor(y);
    if (ymd(s.plant).y < CLIM_START || ymd(s.harvest).y > CLIM_END) continue;
    const c = cumulative(clim, "precip", s.plant, length);
    if (c.some((x) => x == null)) continue;
    curves.push(c as number[]);
    years.push(y);
  }
  const bands: Band[] = [];
  for (let k = 0; k < length; k++) {
    const col = curves.map((c) => c[k]);
    bands.push({ p10: quantile(col, 0.1), p50: quantile(col, 0.5), p90: quantile(col, 0.9) });
  }
  return { bands, years, curves };
}

/**
 * For each 1991-2020 season, the number of days in the first `n` days of the
 * season with Tmax above `thr`. Used to put this season's hot-day count in context.
 */
export function hotDayCounts(clim: Daily, seasonFor: (y: number) => Season, n: number, thr: number): number[] {
  const ix = indexOf(clim);
  const out: number[] = [];
  for (let y = CLIM_START - 1; y <= CLIM_END; y++) {
    const s = seasonFor(y);
    if (ymd(s.plant).y < CLIM_START || ymd(s.plant + n - 1).y > CLIM_END) continue;
    let c = 0;
    let ok = true;
    for (let k = 0; k < n; k++) {
      const i = ix.get(s.plant + k);
      const v = i === undefined ? null : clim.tmax[i];
      if (v == null) { ok = false; break; }
      if (v > thr) c++;
    }
    if (ok) out.push(c);
  }
  return out;
}

// ------------------------------------------------------------ water balance
export interface WaterBalance {
  dayOfSeason: number[];
  kc: number[];
  etc: (number | null)[];
  cumEtc: (number | null)[];
  cumRain: (number | null)[];
  /** Season-to-date totals over days with data */
  totals: { rain: number; effRain: number; etc: number; gap: number; days: number };
}

/**
 * FAO-56 crop water requirement (ETc = Kc x ET0) against rainfall, from
 * planting to `until` (inclusive). Effective rainfall uses the USDA-SCS method
 * per calendar month (pro-rata for partial months), and the irrigation gap is
 * the sum over months of max(0, ETc - Peff).
 */
export function waterBalance(d: Daily, season: Season, p: CropParams, until: Day): WaterBalance | null {
  if (!p.kc || !p.stages) return null;
  const plan = stagePlan(p.stages, season.length);
  const ix = indexOf(d);
  const out: WaterBalance = {
    dayOfSeason: [], kc: [], etc: [], cumEtc: [], cumRain: [],
    totals: { rain: 0, effRain: 0, etc: 0, gap: 0, days: 0 },
  };
  const monthly = new Map<string, { p: number; etc: number; n: number; dim: number }>();
  let cE = 0;
  let cR = 0;
  let broken = false;
  const last = Math.min(until, season.harvest);
  for (let day = season.plant; day <= last; day++) {
    const t = day - season.plant + 1;
    const kc = kcOnDay(p.kc, plan, t);
    const i = ix.get(day);
    const et0 = i === undefined ? null : d.et0[i];
    const pr = i === undefined ? null : d.precip[i];
    out.dayOfSeason.push(t);
    out.kc.push(kc);
    if (et0 == null || pr == null || broken) {
      broken = true;
      out.etc.push(null); out.cumEtc.push(null); out.cumRain.push(null);
      continue;
    }
    const etc = kc * et0;
    cE += etc; cR += pr;
    out.etc.push(etc); out.cumEtc.push(cE); out.cumRain.push(cR);
    const { y, m } = ymd(day);
    const key = `${y}-${m}`;
    const rec = monthly.get(key) ?? { p: 0, etc: 0, n: 0, dim: daysInMonth(y, m) };
    rec.p += pr; rec.etc += etc; rec.n += 1;
    monthly.set(key, rec);
  }
  for (const r of monthly.values()) {
    const pe = effectiveRain(r.p, r.n * (30.4 / r.dim));
    out.totals.rain += r.p;
    out.totals.effRain += pe;
    out.totals.etc += r.etc;
    out.totals.gap += Math.max(0, r.etc - pe);
    out.totals.days += r.n;
  }
  return out;
}

// ---------------------------------------------------------- season totals
export interface SeasonTotal { year: number; rain: number; tmax: number }

/** Total rainfall and mean daily maximum temperature for every complete season in `d`. */
export function seasonTotals(d: Daily, seasonFor: (y: number) => Season, y0: number, y1: number): SeasonTotal[] {
  const ix = indexOf(d);
  const out: SeasonTotal[] = [];
  for (let y = y0; y <= y1; y++) {
    const s = seasonFor(y);
    let rain = 0;
    const temps: number[] = [];
    let complete = true;
    for (let day = s.plant; day <= s.harvest; day++) {
      const i = ix.get(day);
      const pr = i === undefined ? null : d.precip[i];
      const tx = i === undefined ? null : d.tmax[i];
      if (pr == null || tx == null) { complete = false; break; }
      rain += pr;
      temps.push(tx);
    }
    if (complete) out.push({ year: y, rain, tmax: mean(temps) });
  }
  return out;
}

// ------------------------------------------------------------ monthly
export interface MonthStat { y: number; m: number; rain: number; normal: number; pct: number | null }

/** Monthly rainfall for the months fully inside [from, to], vs the 1991-2020 mean for that month. */
export function monthlyVsNormal(obs: Daily, clim: Daily, from: Day, to: Day): MonthStat[] {
  const norm = new Map<number, number[]>();
  const tot = new Map<string, number>();
  clim.day.forEach((day, i) => {
    const { y, m } = ymd(day);
    const p = clim.precip[i];
    if (y < CLIM_START || y > CLIM_END || p == null) return;
    tot.set(`${y}-${m}`, (tot.get(`${y}-${m}`) ?? 0) + p);
  });
  for (const [k, v] of tot) {
    const m = Number(k.split("-")[1]);
    if (!norm.has(m)) norm.set(m, []);
    norm.get(m)!.push(v);
  }
  const months = new Map<string, { y: number; m: number; sum: number; n: number }>();
  obs.day.forEach((day, i) => {
    if (day < from || day > to) return;
    const p = obs.precip[i];
    if (p == null) return;
    const { y, m } = ymd(day);
    const k = `${y}-${m}`;
    const r = months.get(k) ?? { y, m, sum: 0, n: 0 };
    r.sum += p; r.n++;
    months.set(k, r);
  });
  const out: MonthStat[] = [];
  for (const r of months.values()) {
    if (r.n < daysInMonth(r.y, r.m)) continue;
    const normal = mean(norm.get(r.m) ?? []);
    out.push({ y: r.y, m: r.m, rain: r.sum, normal, pct: normal > 0 ? (100 * (r.sum - normal)) / normal : null });
  }
  return out.sort((a, b) => a.y - b.y || a.m - b.m);
}

/** Percentile of today's value against the same-DOY (+/-7 d) 1991-2020 sample. */
export function doyPercentile(clim: Daily, v: Exclude<Vars, "precip">, day: Day, value: number, halfWindow = 7): number {
  const target = dayOfYear(day);
  const sample: number[] = [];
  clim.day.forEach((dd, i) => {
    const y = ymd(dd).y;
    if (y < CLIM_START || y > CLIM_END) return;
    let diff = Math.abs(dayOfYear(dd) - target);
    diff = Math.min(diff, 366 - diff);
    const x = clim[v][i];
    if (diff <= halfWindow && x != null) sample.push(x);
  });
  return percentileRank(finite(sample), value);
}
