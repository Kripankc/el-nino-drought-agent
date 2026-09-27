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

async function cachedJson(url: string, ttlMs: number, status?: Status): Promise<any> {
  try {
    const hit = (await idbGet(url)) as CacheEntry | undefined;
    if (hit && Date.now() - hit.t < ttlMs) return hit.v;
  } catch { /* storage unavailable: fetch instead */ }
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await fetch(url);
    if (r.status === 429) {
      // Free tier: 600 calls/min, 5,000/hour, 10,000/day (weighted by days x variables).
      status?.(`The free weather service allows a limited amount of data per minute. Waiting 65 s, then retrying (attempt ${attempt + 1} of 3). Places you have already opened load instantly.`);
      await new Promise((res) => setTimeout(res, 65_000));
      continue;
    }
    const body = await r.json().catch(() => null);
    if (!r.ok || body?.error) {
      throw new ApiError(`Open-Meteo: ${body?.reason ?? r.status + " " + r.statusText}`);
    }
    try { await idbSet(url, { t: Date.now(), v: body } satisfies CacheEntry); } catch { /* ignore */ }
    return body;
  }
  throw new ApiError("Open-Meteo rate limit: please try again in an hour.");
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

export function mergeDaily(parts: Daily[]): Daily {
  const out: Daily = { day: [], precip: [], tmax: [], tmin: [], et0: [], rh: [], sm: [] };
  const seen = new Set<Day>();
  const rows: [Day, number, Daily][] = [];
  for (const p of parts) p.day.forEach((d, i) => rows.push([d, i, p]));
  rows.sort((a, b) => a[0] - b[0]);
  for (const [d, i, p] of rows) {
    if (seen.has(d)) continue;
    seen.add(d);
    out.day.push(d);
    (["precip", "tmax", "tmin", "et0", "rh", "sm"] as const).forEach((k) => out[k].push(p[k][i]));
  }
  return out;
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
      precipPct: clim != null && clim > 1 && anom != null ? (100 * anom) / clim : null,
    };
  });
}
