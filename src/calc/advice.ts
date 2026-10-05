// Rule-based guidance. Every item states the trigger (the data that fired it)
// and the source of the agronomic statement. Nothing fires without data.
// Items carry a message id and values; the wording (in each language) lives in
// src/i18n/advice.ts.
import { Day, toDay } from "../lib/dates";
import { Season, StagePlan } from "./season";
import { median } from "./stats";
import { EnsoPhase, PhaseImpact, tendency } from "./enso";
import type { EnsembleDay, SeasonalMonth } from "../api/openmeteo";

export type AdviceId =
  | "rain_low" | "soil_dry" | "heat_mid" | "heavy_rain" | "seas_dry" | "seas_wet" | "dry_fortnight"
  | "enso_pending" | "enso_dry_pre" | "enso_dry_in" | "enso_wet" | "enso_none" | "enso_hot";

export type AdviceVars = Record<string, number | string | boolean | number[] | null>;
export interface Advice { id: AdviceId; v: AdviceVars; source: string }

export interface AdviceInput {
  season: Season;                 // season being managed (current, or the next one when off-season)
  inSeason: boolean;
  today: Day;
  plan: StagePlan | null;
  heatC: number | null;
  heatRef: string | null;
  rainPercentile: number | null;  // season-to-date cumulative rain vs 1991-2020
  gapMm: number | null;           // season-to-date irrigation gap (ETc - effective rain)
  smPercentile: number | null;    // root-zone (0-100 cm) soil moisture vs same time of year
  forecast: EnsembleDay[] | null;
  seasonal: SeasonalMonth[] | null;
  /** ENSO phase for the date and, once loaded, how past seasons of that phase went here */
  enso: { phase: EnsoPhase; status: "active" | "developing" | "expected"; impact: PhaseImpact | null; loading: boolean } | null;
  /** Next 15 days: ensemble-median rain total and the 1991-2020 totals for the same dates */
  fc15: { total: number; normal: number; percentile: number } | null;
  references: Record<string, string>;
}

function midWindow(season: Season, plan: StagePlan): [Day, Day] {
  return [season.plant + plan.bounds[1], season.plant + plan.bounds[2] - 1];
}

const FAO33 = "Doorenbos & Kassam (1979), FAO Irrigation and Drainage Paper 33";
const SAVE_GROW = "FAO (2011) Save and Grow: a policymaker's guide to sustainable intensification of smallholder crop production";
const r = Math.round;

export function buildAdvice(x: AdviceInput): Advice[] {
  const out: Advice[] = [];
  const mid = x.plan ? midWindow(x.season, x.plan) : null;
  const midAhead = mid && mid[1] >= x.today ? mid : null;

  // 1. Season-to-date rainfall well below normal with an irrigation gap
  if (x.inSeason && x.rainPercentile != null && x.rainPercentile < 20 && x.gapMm != null && x.gapMm > 25) {
    out.push({ id: "rain_low", v: { pct: r(x.rainPercentile), gap: r(x.gapMm), mid0: midAhead?.[0] ?? null, mid1: midAhead?.[1] ?? null }, source: FAO33 });
  }

  // 2. Very dry root zone
  if (x.smPercentile != null && x.smPercentile < 10) {
    out.push({ id: "soil_dry", v: { pct: r(x.smPercentile) }, source: SAVE_GROW });
  }

  if (x.forecast && x.forecast.length) {
    // 3. Heat in the next 15 days during the sensitive stage
    if (x.heatC != null && mid) {
      const hot = x.forecast.filter((d) => d.day >= mid[0] && d.day <= mid[1] && median(d.members.tmax) > x.heatC!);
      if (hot.length) {
        out.push({ id: "heat_mid", v: { hot: hot.length, n: x.forecast.length, thr: x.heatC }, source: x.heatRef ? x.references[x.heatRef] ?? x.heatRef : "" });
      }
    }
    // 4. Heavy rain in the next 3 days
    let best = 0;
    let bestStart = x.forecast[0].day;
    for (let i = 0; i + 2 < x.forecast.length && i < 13; i++) {
      const s = [0, 1, 2].reduce((a, k) => a + median(x.forecast![i + k].members.precip), 0);
      if (s > best) { best = s; bestStart = x.forecast[i].day; }
    }
    if (best >= 75) out.push({ id: "heavy_rain", v: { mm: r(best), start: bestStart }, source: "General field practice" });
  }

  // 5-6. Seasonal outlook vs SEAS5's own normal during the sensitive stage (in
  // season) or anywhere in the coming season (before sowing)
  const win: [Day, Day] | null = x.inSeason ? mid : [x.season.plant, x.season.harvest];
  if (x.seasonal && win) {
    const inWin = x.seasonal.filter((m) => {
      const start = toDay(m.month + "-01");
      return start <= win[1] && start + 30 >= Math.max(win[0], x.today) && m.precipPct != null;
    });
    const dry = inWin.filter((m) => m.precipPct! <= -20).map((m) => Number(m.month.slice(5, 7)));
    const wet = inWin.filter((m) => m.precipPct! >= 20).map((m) => Number(m.month.slice(5, 7)));
    if (dry.length) out.push({ id: "seas_dry", v: { months: dry, inSeason: x.inSeason }, source: `${FAO33}; seasonal forecasts have limited skill at a single location` });
    if (wet.length) out.push({ id: "seas_wet", v: { months: wet }, source: "General field practice; seasonal forecasts have limited skill at a single location" });
  }

  // 7. Next two weeks much drier than the same dates in 1991-2020
  if (x.fc15 && x.fc15.normal >= 15 && x.fc15.percentile < 20) {
    const soon = !x.inSeason && x.season.plant - x.today <= 30;
    if (x.inSeason || soon) {
      out.push({ id: "dry_fortnight", v: { total: r(x.fc15.total), normal: r(x.fc15.normal), drierThan: r(100 - x.fc15.percentile), inSeason: x.inSeason }, source: x.inSeason ? FAO33 : "General field practice" });
    }
  }

  // 8. ENSO: what past seasons of the current phase did here
  if (x.enso) {
    const base = { phase: x.enso.phase, status: x.enso.status };
    const im = x.enso.impact;
    if (!im) {
      out.push({ id: "enso_pending", v: { ...base, loading: x.enso.loading }, source: "NOAA CPC Relative Oceanic Niño Index" });
    } else {
      // Late in the season a whole-season tendency no longer helps decisions
      const late = x.inSeason && x.season.harvest - x.today < 30;
      const t = late ? null : tendency(im);
      const hist = { ...base, n: im.n, median: r(im.medianRainPct), clear: im.pRain < 0.05 };
      if (t === "dry" && !x.inSeason) {
        out.push({ id: "enso_dry_pre", v: { ...hist, k: im.drier }, source: `${SAVE_GROW}; ask your local extension service which varieties are adapted` });
      } else if (t === "dry") {
        out.push({ id: "enso_dry_in", v: { ...hist, k: im.drier, soFar: x.rainPercentile != null ? r(x.rainPercentile) : null, mid0: midAhead?.[0] ?? null, mid1: midAhead?.[1] ?? null, hasPlan: mid != null }, source: `${FAO33}; ${SAVE_GROW}` });
      } else if (t === "wet") {
        out.push({ id: "enso_wet", v: { ...hist, k: im.wetter }, source: "General field practice" });
      } else if (!late) {
        out.push({ id: "enso_none", v: { ...hist, drier: im.drier, wetter: im.wetter }, source: "ERA5 rainfall by NOAA CPC ENSO episode (this page)" });
      }
      if (x.heatC != null && im.n >= 5 && im.medianTempAnom >= 0.3 && im.pTemp < 0.05) {
        out.push({ id: "enso_hot", v: { ...base, tAnom: Math.round(im.medianTempAnom * 10) / 10, thr: x.heatC }, source: x.heatRef ? x.references[x.heatRef] ?? x.heatRef : "" });
      }
    }
  }
  return out;
}
