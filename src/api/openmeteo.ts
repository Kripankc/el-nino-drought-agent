// Open-Meteo clients. All calls go straight from the browser (Open-Meteo sends
// CORS headers). Free, non-commercial use; attribution: "Weather data by Open-Meteo.com".
import { get as idbGet, set as idbSet } from "idb-keyval";
import { Day, fromDay, toDay, todayDay } from "../lib/dates";
import { Daily } from "../calc/climate";

const ARCHIVE = "https://archive-api.open-meteo.com/v1/archive";
const ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble";
const SEASONAL = "https://seasonal-api.open-meteo.com/v1/seasonal";

/** ERA5 daily variables requested from the archive (model pinned to ERA5). */
export const DAILY_VARS = {
  precip: "precipitation_sum",
  tmax: "temperature_2m_max",
  tmin: "temperature_2m_min",
  et0: "et0_fao_evapotranspiration",
  rh: "relative_humidity_2m_mean",
  sm: "soil_moisture_0_to_100cm_mean",
} as const;
type VarKey = keyof typeof DAILY_VARS;

/** ERA5 is published with about 5 days' delay. */
export const ERA5_LAG_DAYS = 6;
export function lastEra5Day(): Day { return todayDay() - ERA5_LAG_DAYS; }

export type Status = (msg: string) => void;

export class ApiError extends Error {}

/** ERA5 grid is 0.25 deg; snapping requests to it maximises cache reuse. */
export function snap(x: number): number {
  return Math.round(x * 4) / 4;
}

interface CacheEntry { t: number; v: unknown }

// ---------------------------------------------------------------- rate budget
// Open-Meteo's free tier allows 600 weighted calls per minute per visitor. A call
// weighs max(1, days/14 x variables/10) per location (open-meteo/open-meteo,
// ForecastApiResult.calculateQueryWeight). We keep our own running total and
// wait before a request that would exceed the budget, instead of hitting 429.
const BUDGET_PER_MIN = 540;
const spent: { t: number; w: number }[] = [];

export function requestWeight(url: string): number {
  const u = new URL(url);
  const p = u.searchParams;
  const vars = ["daily", "hourly", "monthly", "weekly"].reduce((n, k) => n + (p.get(k)?.split(",").filter(Boolean).length ?? 0), 0);
  let days = 14;
  const a = p.get("start_date");
  const b = p.get("end_date");
  if (a && b) days = toDay(b) - toDay(a) + 1;
  else if (p.get("forecast_days")) days = Number(p.get("forecast_days"));
  const locations = (p.get("latitude") ?? "").split(",").length;
  return locations * Math.max(1, (days / 14) * (vars / 10));
}

async function reserve(w: number, status?: Status) {
  for (;;) {
    const now = Date.now();
    while (spent.length && now - spent[0].t > 61_000) spent.shift();
    const used = spent.reduce((a, x) => a + x.w, 0);
    if (used + w <= BUDGET_PER_MIN || !spent.length) { spent.push({ t: now, w }); return; }
    const wait = 61_000 - (now - spent[0].t);
    status?.(`Pacing requests to the free weather service (${Math.ceil(wait / 1000)} s)…`);
    await new Promise((res) => setTimeout(res, Math.min(wait, 5_000)));
  }
}

// Open-Meteo also refuses more than a few simultaneous requests from one
// visitor ("Too many concurrent requests"), so every call goes through one
// small queue.
const MAX_IN_FLIGHT = 3;
let inFlight = 0;
const waiting: (() => void)[] = [];
async function slot(): Promise<() => void> {
  if (inFlight >= MAX_IN_FLIGHT) await new Promise<void>((res) => waiting.push(res));
  inFlight++;
  return () => { inFlight--; waiting.shift()?.(); };
}

async function cachedJson(url: string, ttlMs: number, status?: Status): Promise<any> {
  try {
    const hit = (await idbGet(url)) as CacheEntry | undefined;
    if (hit && Date.now() - hit.t < ttlMs) return hit.v;
  } catch { /* storage unavailable: fetch instead */ }
  for (let attempt = 0; attempt < 6; attempt++) {
    await reserve(requestWeight(url), status);
    const release = await slot();
    let r: Response;
    let body: any;
    try {
      r = await fetch(url);
      body = await r.json().catch(() => null);
    } finally {
      release();
    }
    if (r.status === 429) {
      const reason = String(body?.reason ?? "");
      if (/concurrent/i.test(reason)) {
        await new Promise((res) => setTimeout(res, 500 * 2 ** attempt)); // short back-off
        continue;
      }
      // Minutely / hourly / daily quota: say which, and wait
      status?.(`${reason || "The free weather service limit is reached."} Retrying in 60 s.`);
      await new Promise((res) => setTimeout(res, 60_000));
      continue;
    }
    if (!r.ok || body?.error) {
      throw new ApiError(`Open-Meteo: ${body?.reason ?? r.status + " " + r.statusText}`);
    }
    try { await idbSet(url, { t: Date.now(), v: body } satisfies CacheEntry); } catch { /* ignore */ }
    return body;
  }
  throw new ApiError("The free weather service is not responding to more requests right now. Please try again in a few minutes.");
}

export interface GridInfo { latitude: number; longitude: number; elevation: number }

export async function era5Daily(
  lat: number, lon: number, from: Day, to: Day, vars: VarKey[], status?: Status,
): Promise<{ data: Daily; grid: GridInfo }> {
  const end = Math.min(to, lastEra5Day());
  const params = new URLSearchParams({
    latitude: String(snap(lat)),
    longitude: String(snap(lon)),
    start_date: fromDay(from),
    end_date: fromDay(end),
    daily: vars.map((v) => DAILY_VARS[v]).join(","),
    models: "era5",
    timezone: "GMT",
  });
  // Fully historical requests never change; recent ones are refreshed daily.
  const ttl = end < todayDay() - 60 ? 365 * 86_400_000 : 12 * 3_600_000;
  const j = await cachedJson(`${ARCHIVE}?${params}`, ttl, status);
  const d = j.daily ?? {};
  const pick = (k: VarKey) => (vars.includes(k) ? (d[DAILY_VARS[k]] as (number | null)[]) : undefined);
  const n = (d.time as string[]).length;
  const empty = () => new Array<number | null>(n).fill(null);
  return {
    data: {
      day: (d.time as string[]).map(toDay),
      precip: pick("precip") ?? empty(), tmax: pick("tmax") ?? empty(), tmin: pick("tmin") ?? empty(),
      et0: pick("et0") ?? empty(), rh: pick("rh") ?? empty(), sm: pick("sm") ?? empty(),
    },
    grid: { latitude: j.latitude, longitude: j.longitude, elevation: j.elevation },
  };
}

const KEYS = ["precip", "tmax", "tmin", "et0", "rh", "sm"] as const;

/** Merge daily series; for each day and variable the first non-null value wins. */
export function mergeDaily(parts: Daily[]): Daily {
  const byDay = new Map<Day, Record<(typeof KEYS)[number], number | null>>();
  for (const p of parts) {
    p.day.forEach((d, i) => {
      const r = byDay.get(d) ?? { precip: null, tmax: null, tmin: null, et0: null, rh: null, sm: null };
      for (const k of KEYS) if (r[k] == null && p[k][i] != null) r[k] = p[k][i];
      byDay.set(d, r);
    });
  }
  const days = [...byDay.keys()].sort((a, b) => a - b);
  const out: Daily = { day: days, precip: [], tmax: [], tmin: [], et0: [], rh: [], sm: [] };
  for (const d of days) for (const k of KEYS) out[k].push(byDay.get(d)![k]);
  return out;
}

/** Merge overlapping or touching [from, to] windows. */
export function mergeWindows(ws: [Day, Day][]): [Day, Day][] {
  const s = ws.filter(([a, b]) => b >= a).sort((x, y) => x[0] - y[0]);
  const out: [Day, Day][] = [];
  for (const w of s) {
    const last = out[out.length - 1];
    if (last && w[0] <= last[1] + 1) last[1] = Math.max(last[1], w[1]);
    else out.push([w[0], w[1]]);
  }
  return out;
}

/**
 * Fetch many short ERA5 windows instead of one long record. Weight is charged
 * per request with a minimum of 1, so 30 seasonal windows cost far less than
 * 30 full years.
 */
export async function era5Windows(lat: number, lon: number, windows: [Day, Day][], vars: VarKey[], status?: Status, concurrency = 3): Promise<Daily> {
  const ws = mergeWindows(windows.map(([a, b]) => [a, Math.min(b, lastEra5Day())] as [Day, Day]));
  const parts: Daily[] = [];
  let next = 0;
  const worker = async () => {
    while (next < ws.length) {
      const [a, b] = ws[next++];
      parts.push((await era5Daily(lat, lon, a, b, vars, status)).data);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, ws.length) }, worker));
  return mergeDaily(parts);
}

// ------------------------------------------------------------- forecasts
export interface EnsembleDay { day: Day; members: { precip: number[]; tmax: number[]; tmin: number[] } }

/** ECMWF IFS 0.25 deg ensemble (control + 50 members), 15 days. */
export async function ensembleForecast(lat: number, lon: number, status?: Status): Promise<{ days: EnsembleDay[]; model: string }> {
  const params = new URLSearchParams({
    latitude: String(snap(lat)), longitude: String(snap(lon)),
    daily: "precipitation_sum,temperature_2m_max,temperature_2m_min",
    models: "ecmwf_ifs025_ensemble", forecast_days: "15", timezone: "GMT",
  });
  const j = await cachedJson(`${ENSEMBLE}?${params}`, 3 * 3_600_000, status);
  const d = j.daily;
  const collect = (prefix: string) =>
    Object.keys(d).filter((k) => k === prefix || k.startsWith(prefix + "_member"));
  const keys = { precip: collect("precipitation_sum"), tmax: collect("temperature_2m_max"), tmin: collect("temperature_2m_min") };
  if (!keys.precip.length) throw new ApiError("Ensemble response had no precipitation members");
  const days: EnsembleDay[] = (d.time as string[]).map((t, i) => ({
    day: toDay(t),
    members: {
      precip: keys.precip.map((k) => d[k][i]).filter((x: unknown) => typeof x === "number"),
      tmax: keys.tmax.map((k) => d[k][i]).filter((x: unknown) => typeof x === "number"),
      tmin: keys.tmin.map((k) => d[k][i]).filter((x: unknown) => typeof x === "number"),
    },
  })).filter((x: EnsembleDay) => x.members.precip.length > 0);
  return { days, model: "ECMWF IFS 0.25° ensemble" };
}

export interface SeasonalMonth { month: string; precipMm: number | null; precipAnomMm: number | null; tAnom: number | null; precipPct: number | null }

/**
 * ECMWF SEAS5 monthly ensemble-mean values and anomalies against SEAS5's own
 * hindcast climatology. Precipitation is in mm per month.
 */
export async function seasonalMonthly(lat: number, lon: number, status?: Status): Promise<SeasonalMonth[]> {
  const params = new URLSearchParams({
    latitude: String(snap(lat)), longitude: String(snap(lon)),
    monthly: "precipitation_mean,precipitation_anomaly,temperature_2m_mean,temperature_2m_anomaly",
  });
  const j = await cachedJson(`${SEASONAL}?${params}`, 12 * 3_600_000, status);
  const m = j.monthly;
  if (!m) throw new ApiError("Seasonal response had no monthly block");
  const key = (p: string) => Object.keys(m).find((k) => k === p || k.startsWith(p + "_"));
  const pm = key("precipitation_mean");
  const pa = key("precipitation_anomaly");
  const ta = key("temperature_2m_anomaly");
  if (!pm || !pa) throw new ApiError("Seasonal response had no precipitation fields");
  return (m.time as string[]).map((t, i) => {
    const mean = m[pm][i] as number | null;
    const anom = m[pa][i] as number | null;
    const clim = mean != null && anom != null ? mean - anom : null;
    return {
      month: t.slice(0, 7),
      precipMm: mean,
      precipAnomMm: anom,
      tAnom: ta ? (m[ta][i] as number | null) : null,
      precipPct: clim != null && clim >= 10 && anom != null ? (100 * anom) / clim : null, // % is meaningless in near-dry months
    };
  });
}
