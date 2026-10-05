import { Day, ymd } from "../lib/dates";
import { Season } from "./season";
import { SeasonTotal } from "./climate";
import { detrend, mean, median, rankPermutationTest } from "./stats";

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
