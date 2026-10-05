import { Day, ymd } from "../lib/dates";
import { Season } from "./season";
import { CLIM_END, CLIM_START, Daily, SeasonTotal, cumulative, indexOf } from "./climate";
import { detrend, finite, mean, median, rankPermutationTest } from "./stats";

export type Phase = "El Nino" | "La Nina" | "Neutral";

export interface EnsoData {
  generated_utc: string;
  index: "RONI" | "ONI";
  index_source: string;
  definition: string;
  start: string;                 // "YYYY-MM" of values[0] (centre month)
  values: (number | null)[];
  episodes: { type: "El Nino" | "La Nina"; start: string; end: string; peak: number }[];
  run_in_progress: { type: string; seasons_so_far: number } | null;
  latest: { month: string; value: number | null };
  seas5_nino34: null | { source: string; description: string; months: string[]; anomaly_c: (number | null)[] };
}

export function episodeMonths(e: EnsoData): Map<string, Phase> {
  const m = new Map<string, Phase>();
  for (const ep of e.episodes) {
    let [y, mo] = ep.start.split("-").map(Number);
    const [y1, m1] = ep.end.split("-").map(Number);
    while (y < y1 || (y === y1 && mo <= m1)) {
      m.set(`${y}-${mo}`, ep.type);
      mo++;
      if (mo === 13) { mo = 1; y++; }
    }
  }
  return m;
}

export function indexValue(e: EnsoData, y: number, m: number): number | null {
  const [y0, m0] = e.start.split("-").map(Number);
  const i = (y - y0) * 12 + (m - m0);
  return i >= 0 && i < e.values.length ? e.values[i] : null;
}

/** Phase of a season: the ENSO episode type covering more than half its days, else Neutral. */
export function seasonPhase(months: Map<string, Phase>, s: Season): Phase {
  let nino = 0;
  let nina = 0;
  const n = s.harvest - s.plant + 1;
  for (let d: Day = s.plant; d <= s.harvest; d++) {
    const { y, m } = ymd(d);
    const ph = months.get(`${y}-${m}`);
    if (ph === "El Nino") nino++;
    else if (ph === "La Nina") nina++;
  }
  if (nino / n > 0.5) return "El Nino";
  if (nina / n > 0.5) return "La Nina";
  return "Neutral";
}

export interface CompositePoint { year: number; phase: Phase; rainPct: number; tempAnom: number; rain: number }

export interface Composite {
  points: CompositePoint[];
  normalRain: number;              // 1991-2020 mean season rainfall
  byPhase: Record<Phase, { n: number; medianRainPct: number; drierCount: number; medianTempAnom: number }>;
  pRainNinoVsNeutral: number;      // rank-based permutation test p-value
  pTempNinoVsNeutral: number;
  firstYear: number;
  lastYear: number;
}

/**
 * El Nino / La Nina composites of season rainfall and temperature.
 * Rainfall: % departure from the 1991-2020 mean season total.
 * Temperature (mean daily maximum): departure from a linear trend fitted over all seasons (removes
 * the warming trend so it is not mistaken for an ENSO signal).
 */
export function composite(totals: SeasonTotal[], seasonFor: (y: number) => Season, enso: EnsoData): Composite | null {
  if (totals.length < 20) return null;
  const months = episodeMonths(enso);
  const normalSeasons = totals.filter((t) => {
    const s = seasonFor(t.year);
    return ymd(s.plant).y >= 1991 && ymd(s.harvest).y <= 2020;
  });
  const normalRain = mean(normalSeasons.map((t) => t.rain));
  if (!(normalRain > 0)) return null;
  const tRes = detrend(totals.map((t) => t.year), totals.map((t) => t.tmax));
  const points: CompositePoint[] = totals.map((t, i) => ({
    year: t.year,
    phase: seasonPhase(months, seasonFor(t.year)),
    rain: t.rain,
    rainPct: (100 * (t.rain - normalRain)) / normalRain,
    tempAnom: tRes[i],
  }));
  const phases: Phase[] = ["El Nino", "Neutral", "La Nina"];
  const byPhase = {} as Composite["byPhase"];
  for (const ph of phases) {
    const pts = points.filter((p) => p.phase === ph);
    byPhase[ph] = {
      n: pts.length,
      medianRainPct: median(pts.map((p) => p.rainPct)),
      drierCount: pts.filter((p) => p.rainPct < 0).length,
      medianTempAnom: median(pts.map((p) => p.tempAnom)),
    };
  }
  const nino = points.filter((p) => p.phase === "El Nino");
  const neu = points.filter((p) => p.phase === "Neutral");
  return {
    points,
    normalRain,
    byPhase,
    pRainNinoVsNeutral: rankPermutationTest(nino.map((p) => p.rainPct), neu.map((p) => p.rainPct)),
    pTempNinoVsNeutral: rankPermutationTest(nino.map((p) => p.tempAnom), neu.map((p) => p.tempAnom)),
    firstYear: totals[0].year,
    lastYear: totals[totals.length - 1].year,
  };
}

// ------------------------------------------------------------------ impact of the current phase
export type EnsoPhase = "El Nino" | "La Nina";

export interface MonthImpact {
  m: number;                // calendar month 1-12
  days: number;             // days of this month inside the season
  from: number;             // first and last day of season (0-based offsets) in this month
  to: number;
  normal: number;           // 1991-2020 mean rain over those days (mm)
  medianPct: number | null; // median % departure across phase seasons (null if normal < 10 mm)
}

export interface PhaseImpact {
  phase: EnsoPhase;
  n: number;
  drier: number;
  wetter: number;
  medianRainPct: number;
  medianTempAnom: number;
  pRain: number;              // phase vs neutral, rank permutation test
  pTemp: number;
  years: number[];
  rainPcts: number[];         // aligned with years
  /** Seasons in strong events (|episode peak| >= 1.5), if at least 3 */
  strong: { n: number; drier: number; medianRainPct: number; years: number[] } | null;
  /** Most recent completed phase season (excluding `exclude`) */
  last: { year: number; rainPct: number; tempAnom: number; peak: number | null } | null;
  months: MonthImpact[];
  /** Median accumulated rain since sowing across phase seasons, per day of season */
  curve: (number | null)[];
  lastCurve: (number | null)[] | null;
}

/** Peak index value of the episode that covers the most months of a season. */
export function seasonPeak(e: EnsoData, s: Season, phase: EnsoPhase): number | null {
  let best: { n: number; peak: number } | null = null;
  for (const ep of e.episodes) {
    if (ep.type !== phase) continue;
    const a = toDayYM(ep.start, false);
    const b = toDayYM(ep.end, true);
    const n = Math.min(b, s.harvest) - Math.max(a, s.plant) + 1;
    if (n > 0 && (!best || n > best.n)) best = { n, peak: ep.peak };
  }
  return best?.peak ?? null;
}

function toDayYM(ym: string, end: boolean): Day {
  const [y, m] = ym.split("-").map(Number);
  return end ? Math.round(Date.UTC(y, m, 0) / 86_400_000) : Math.round(Date.UTC(y, m - 1, 1) / 86_400_000);
}

/**
 * What seasons of one ENSO phase looked like at this place: season totals,
 * month-by-month departures and the typical accumulation curve. `exclude`
 * removes the season being examined so it is not compared with itself.
 */
export function phaseImpact(
  all: Daily, comp: Composite, seasonFor: (y: number) => Season, enso: EnsoData,
  phase: EnsoPhase, exclude: number | null = null,
): PhaseImpact | null {
  const pts = comp.points.filter((p) => p.year !== exclude);
  const ph = pts.filter((p) => p.phase === phase);
  const neu = pts.filter((p) => p.phase === "Neutral");
  if (ph.length < 3) return null;
  const length = seasonFor(ph[0].year).length + 1;
  const ix = indexOf(all);

  // Month-by-month: rain over the days of each calendar month that fall in the season
  const ref = seasonFor(ph[0].year);
  const monthsOf: { m: number; offs: number[] }[] = [];
  for (let k = 0; k < length; k++) {
    const m = ymd(ref.plant + k).m;
    const last = monthsOf[monthsOf.length - 1];
    if (last && last.m === m) last.offs.push(k); else monthsOf.push({ m, offs: [k] });
  }
  const sumOver = (y: number, offs: number[]): number | null => {
    const s = seasonFor(y);
    let acc = 0;
    for (const k of offs) {
      const v = all.precip[ix.get(s.plant + k) ?? -1];
      if (v == null) return null;
      acc += v;
    }
    return acc;
  };
  const normalYears = pts.filter((p) => {
    const s = seasonFor(p.year);
    return ymd(s.plant).y >= CLIM_START && ymd(s.harvest).y <= CLIM_END;
  }).map((p) => p.year);
  const months: MonthImpact[] = monthsOf.filter((mo) => mo.offs.length >= 10).map((mo) => {
    const normal = mean(finite(normalYears.map((y) => sumOver(y, mo.offs))));
    const pcts = normal >= 10 ? finite(ph.map((p) => { const v = sumOver(p.year, mo.offs); return v == null ? null : (100 * (v - normal)) / normal; })) : [];
    return { m: mo.m, days: mo.offs.length, from: mo.offs[0], to: mo.offs[mo.offs.length - 1], normal, medianPct: pcts.length >= 3 ? median(pcts) : null };
  });

  // Typical accumulation curve
  const curves = ph.map((p) => cumulative(all, "precip", seasonFor(p.year).plant, length));
  const curve = Array.from({ length }, (_, k) => {
    const col = finite(curves.map((c) => c[k]));
    return col.length >= 3 ? median(col) : null;
  });

  // "Last" means the most recent one before the season being examined
  const before = exclude != null ? ph.filter((p) => p.year < exclude) : ph;
  const lastP = before.length ? before[before.length - 1] : null;
  const peaks = ph.map((p) => ({ p, peak: seasonPeak(enso, seasonFor(p.year), phase) }));
  const strongPts = peaks.filter((x) => x.peak != null && Math.abs(x.peak) >= 1.5).map((x) => x.p);
  return {
    phase,
    n: ph.length,
    drier: ph.filter((p) => p.rainPct < 0).length,
    wetter: ph.filter((p) => p.rainPct > 0).length,
    medianRainPct: median(ph.map((p) => p.rainPct)),
    medianTempAnom: median(ph.map((p) => p.tempAnom)),
    pRain: rankPermutationTest(ph.map((p) => p.rainPct), neu.map((p) => p.rainPct)),
    pTemp: rankPermutationTest(ph.map((p) => p.tempAnom), neu.map((p) => p.tempAnom)),
    years: ph.map((p) => p.year),
    rainPcts: ph.map((p) => p.rainPct),
    strong: strongPts.length >= 3
      ? { n: strongPts.length, drier: strongPts.filter((p) => p.rainPct < 0).length, medianRainPct: median(strongPts.map((p) => p.rainPct)), years: strongPts.map((p) => p.year) }
      : null,
    last: lastP ? { year: lastP.year, rainPct: lastP.rainPct, tempAnom: lastP.tempAnom, peak: seasonPeak(enso, seasonFor(lastP.year), phase) } : null,
    months,
    curve,
    lastCurve: lastP ? cumulative(all, "precip", seasonFor(lastP.year).plant, length) : null,
  };
}

/** Tendency of a phase at this place: "dry", "wet" or null when there is no clear signal. */
export function tendency(x: PhaseImpact): "dry" | "wet" | null {
  if (x.n < 5) return null;
  const share = Math.max(x.drier, x.wetter) / x.n;
  if (x.medianRainPct < 0 && x.drier >= x.wetter && (x.pRain < 0.05 || share >= 0.6)) return "dry";
  if (x.medianRainPct > 0 && x.wetter > x.drier && (x.pRain < 0.05 || share >= 0.6)) return "wet";
  return null;
}

/**
 * ENSO state for the selected date. Current mode: the latest index value, a
 * run in progress, or the SEAS5 Nino-3.4 mean over the next six months
 * (expected). Past mode: whether the month lies in an official episode.
 */
export interface EnsoState { phase: EnsoPhase; status: "active" | "developing" | "expected"; value: number | null }

export function ensoState(e: EnsoData, D: Day, current: boolean): EnsoState | null {
  if (!current) {
    const { y, m } = ymd(D);
    const ph = episodeMonths(e).get(`${y}-${m}`);
    return ph && ph !== "Neutral" ? { phase: ph, status: "active", value: indexValue(e, y, m) } : null;
  }
  const v = e.latest.value;
  const run = e.run_in_progress;
  if (run && (run.type === "El Nino" || run.type === "La Nina")) {
    return { phase: run.type, status: run.seasons_so_far >= 5 ? "active" : "developing", value: v };
  }
  if (v != null && Math.abs(v) >= 0.5) return { phase: v > 0 ? "El Nino" : "La Nina", status: "developing", value: v };
  const f = finite(e.seas5_nino34?.anomaly_c ?? []);
  if (f.length >= 3) {
    const mf = mean(f);
    if (Math.abs(mf) >= 0.5) return { phase: mf > 0 ? "El Nino" : "La Nina", status: "expected", value: v };
  }
  return null;
}
