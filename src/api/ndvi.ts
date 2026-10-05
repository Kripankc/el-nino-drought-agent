// MODIS MOD13Q1 v061 NDVI (250 m, 16-day composites) for one pixel, from the
// ORNL DAAC MODIS Web Service (free, no key). Only composites whose pixel
// reliability is good (0) or marginal (1) are kept, so cloudy values drop out.
import { get as idbGet, set as idbSet } from "idb-keyval";
import { Day, dayOfYear, toDay, todayDay, ymd } from "../lib/dates";

const BASE = "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset";
const CHUNK = 144;            // days per request: at most 10 composites (service limit)
const TTL = 3 * 86_400_000;   // recent composites are added every 16 days

export interface NdviPoint { day: Day; ndvi: number }

const modisDate = (d: Day) => `A${ymd(d).y}${String(dayOfYear(d)).padStart(3, "0")}`;

async function band(lat: number, lon: number, a: Day, b: Day, name: string): Promise<Map<string, number>> {
  const url = `${BASE}?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}&band=${name}&startDate=${modisDate(a)}&endDate=${modisDate(b)}&kmAboveBelow=0&kmLeftRight=0`;
  const complete = b < todayDay() - 40;
  const hit = await idbGet(url).catch(() => undefined) as { t: number; v: [string, number][] } | undefined;
  if (hit && (complete || Date.now() - hit.t < TTL)) return new Map(hit.v);
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`MODIS NDVI service: HTTP ${r.status}`);
  const j = await r.json() as { subset?: { calendar_date: string; data: number[] }[] };
  const v: [string, number][] = (j.subset ?? []).map((s) => [s.calendar_date, s.data[0]]);
  idbSet(url, { t: Date.now(), v }).catch(() => undefined);
  return new Map(v);
}

/** Cloud-screened NDVI between two days (composite start dates). */
export async function ndviSeries(lat: number, lon: number, from: Day, to: Day): Promise<NdviPoint[]> {
  const out: NdviPoint[] = [];
  const chunks: [Day, Day][] = [];
  for (let a = from; a <= to; a += CHUNK + 1) chunks.push([a, Math.min(to, a + CHUNK)]);
  for (const [a, b] of chunks) {
    const [v, q] = await Promise.all([band(lat, lon, a, b, "250m_16_days_NDVI"), band(lat, lon, a, b, "250m_16_days_pixel_reliability")]);
    for (const [date, raw] of v) {
      const rel = q.get(date);
      if (rel == null || rel > 1 || raw <= -2000) continue;
      out.push({ day: toDay(date) + 8, ndvi: raw * 0.0001 }); // centre of the 16-day composite
    }
  }
  return out.sort((x, y) => x.day - y.day);
}
