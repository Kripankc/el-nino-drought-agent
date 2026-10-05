// Rule-based guidance. Every item states the trigger (the data that fired it)
// and the source of the agronomic statement. Nothing fires without data.
import { Day, fmtDay, monthName, toDay } from "../lib/dates";
import { Season, StagePlan } from "./season";
import { median } from "./stats";
import { EnsoPhase, PhaseImpact, tendency } from "./enso";
import type { EnsembleDay, SeasonalMonth } from "../api/openmeteo";

export interface Advice { title: string; trigger: string; action: string; source: string }

export interface AdviceInput {
  cropLabel: string;
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

export function buildAdvice(x: AdviceInput): Advice[] {
  const out: Advice[] = [];
  const fao33 = "Doorenbos & Kassam (1979), FAO Irrigation and Drainage Paper 33";
  const mid = x.plan ? midWindow(x.season, x.plan) : null;

  // 1. Season-to-date rainfall well below normal with an irrigation gap
  if (x.inSeason && x.rainPercentile != null && x.rainPercentile < 20 && x.gapMm != null && x.gapMm > 25) {
    out.push({
      title: "Rain since sowing is well below normal",
      trigger: `Season rainfall so far is at the ${Math.round(x.rainPercentile)}th percentile of 1991–2020, and the crop has needed about ${Math.round(x.gapMm)} mm more water than effective rain supplied.`,
      action: mid
        ? `If water for irrigation is limited, save it for the mid-season stage (${fmtDay(mid[0])} – ${fmtDay(mid[1])}), when water shortage reduces yield the most.`
        : "If water for irrigation is limited, save it for flowering and grain or yield formation, when water shortage reduces yield the most.",
      source: fao33,
    });
  }

  // 2. Very dry root zone
  if (x.smPercentile != null && x.smPercentile < 10) {
    out.push({
      title: "Soil is unusually dry for the time of year",
      trigger: `ERA5 root-zone soil moisture (0–100 cm) is at the ${Math.round(x.smPercentile)}th percentile for this time of year (1991–2020).`,
      action: "Reduce evaporation from the soil surface, for example by keeping crop residue or mulch on the field.",
      source: "FAO (2011) Save and Grow: a policymaker's guide to sustainable intensification of smallholder crop production",
    });
  }

  if (x.forecast && x.forecast.length) {
    // 3. Heat in the next 15 days during the sensitive stage
    if (x.heatC != null && mid) {
      const hot = x.forecast.filter((d) => d.day >= mid[0] && d.day <= mid[1] && median(d.members.tmax) > x.heatC!);
      if (hot.length) {
        out.push({
          title: `Heat forecast during the mid-season stage`,
          trigger: `On ${hot.length} of the next ${x.forecast.length} days the ensemble median maximum temperature is above ${x.heatC} °C, while ${x.cropLabel} is in its mid-season stage.`,
          action: "Temperatures above this level during flowering are linked to yield loss. Where irrigation is available, avoid letting the crop run short of water during these days.",
          source: x.heatRef ? x.references[x.heatRef] ?? x.heatRef : "",
        });
      }
    }
    // 4. Heavy rain in the next 3 days
    let best = 0;
    let bestStart = x.forecast[0].day;
    for (let i = 0; i + 2 < x.forecast.length && i < 13; i++) {
      const s = [0, 1, 2].reduce((a, k) => a + median(x.forecast![i + k].members.precip), 0);
      if (s > best) { best = s; bestStart = x.forecast[i].day; }
    }
    if (best >= 75) {
      out.push({
        title: "Heavy rain possible",
        trigger: `The ensemble median gives about ${Math.round(best)} mm over three days starting ${fmtDay(bestStart)}.`,
        action: "Clear field drains and avoid applying fertiliser or pesticide just before the rain, so it is not washed off.",
        source: "General field practice",
      });
    }
  }

  // 5. Seasonal outlook: drier than SEAS5's own normal during the sensitive stage
  //    (in season), or anywhere in the coming season (before sowing).
  const win: [Day, Day] | null = x.inSeason ? mid : [x.season.plant, x.season.harvest];
  if (x.seasonal && win) {
    const dryMonths = x.seasonal.filter((m) => {
      const start = toDay(m.month + "-01");
      return start <= win[1] && start + 30 >= Math.max(win[0], x.today) && m.precipPct != null && m.precipPct <= -20;
    });
    if (dryMonths.length) {
      const names = dryMonths.map((m) => monthName(Number(m.month.slice(5, 7)))).join(", ");
      out.push({
        title: x.inSeason ? "Seasonal forecast leans dry for the sensitive stage" : "Seasonal forecast leans dry for the coming season",
        trigger: `ECMWF SEAS5 ensemble-mean rainfall for ${names} is at least 20% below the model's own normal.`,
        action: x.inSeason
          ? "Plan now for supplementary irrigation or water harvesting around flowering, and keep soil cover to hold moisture."
          : "If you have not sown yet, discuss shorter-duration or drought-tolerant varieties with your extension office.",
        source: `${fao33}; seasonal forecasts have limited skill at a single location`,
      });
    }
  }

  // 6. Wetter than SEAS5's own normal
  if (x.seasonal && win) {
    const wetMonths = x.seasonal.filter((m) => {
      const start = toDay(m.month + "-01");
      return start <= win[1] && start + 30 >= Math.max(win[0], x.today) && m.precipPct != null && m.precipPct >= 20;
    });
    if (wetMonths.length) {
      out.push({
        title: "Seasonal forecast leans wet",
        trigger: `ECMWF SEAS5 ensemble-mean rainfall for ${wetMonths.map((m) => monthName(Number(m.month.slice(5, 7)))).join(", ")} is at least 20% above the model's own normal.`,
        action: "Check that field drains and bunds are in order, and plan fertiliser applications in splits so less is washed out.",
        source: "General field practice; seasonal forecasts have limited skill at a single location",
      });
    }
  }

  // 7. Next two weeks much drier than the same dates in 1991-2020
  if (x.fc15 && x.fc15.normal >= 15 && x.fc15.percentile < 20) {
    const soon = !x.inSeason && x.season.plant - x.today <= 30;
    if (x.inSeason || soon) {
      out.push({
        title: "The next two weeks look dry",
        trigger: `The ECMWF ensemble median gives ${Math.round(x.fc15.total)} mm over the next 15 days. The same dates in 1991–2020 had a median of ${Math.round(x.fc15.normal)} mm (ERA5), so this is drier than ${Math.round(100 - x.fc15.percentile)}% of those years.`,
        action: x.inSeason
          ? "Check soil moisture and plan irrigation for the next two weeks, giving priority to fields that are flowering."
          : "Wait for enough rain to wet the soil before sowing; seed sown into dry soil may fail to establish.",
        source: x.inSeason ? fao33 : "General field practice",
      });
    }
  }

  // 8. ENSO: what past seasons of the current phase did here
  if (x.enso) {
    const name = x.enso.phase === "El Nino" ? "El Niño" : "La Niña";
    const now = { active: `${name} is under way`, developing: `${name} is developing`, expected: `${name} is forecast` }[x.enso.status];
    const im = x.enso.impact;
    if (!im) {
      out.push({
        title: `${now}`,
        trigger: "NOAA CPC Relative Oceanic Niño Index and the ECMWF SEAS5 Niño-3.4 forecast.",
        action: x.enso.loading ? `Checking how past ${name} seasons went here…` : `See how past ${name} seasons went here, under "${name} impact here".`,
        source: "NOAA CPC Relative Oceanic Niño Index",
      });
    } else {
      const t = tendency(im);
      const clear = im.pRain < 0.05;
      const hist = `In ${t === "wet" ? im.wetter : im.drier} of ${im.n} past ${name} seasons here, rain for this crop season was ${t === "wet" ? "above" : "below"} the 1991–2020 normal (median ${Math.round(im.medianRainPct) > 0 ? "+" : ""}${Math.round(im.medianRainPct)}%)${clear ? "." : "; the difference from neutral seasons is not statistically clear."}`;
      const saveGrow = "FAO (2011) Save and Grow: a policymaker's guide to sustainable intensification of smallholder crop production";
      if (t === "dry" && !x.inSeason) {
        out.push({
          title: "Prepare for a drier season than normal",
          trigger: `${now}. ${hist}`,
          action: "If a shorter-duration or drought-tolerant variety suited to your area is available, consider it. Sow once the soil is moist enough, and have water harvesting and soil cover (crop residue or mulch) ready before the season.",
          source: `${saveGrow}; ask your local extension service which varieties are adapted`,
        });
      } else if (t === "dry") {
        out.push({
          title: "Expect the rest of the season to stay drier than normal",
          trigger: `${now}. ${hist}`,
          action: mid
            ? `Keep crop residue or mulch on the soil and keep weeds down so they do not take water. Save irrigation water for the mid-season stage (${fmtDay(mid[0])} – ${fmtDay(mid[1])}).`
            : "Keep crop residue or mulch on the soil and keep weeds down so they do not take water. Save irrigation water for flowering.",
          source: `${fao33}; ${saveGrow}`,
        });
      } else if (t === "wet") {
        out.push({
          title: "Prepare for a wetter season than normal",
          trigger: `${now}. ${hist}`,
          action: "Clear field drains, check for fungal disease after long wet spells, and split fertiliser applications so less is washed out.",
          source: "General field practice",
        });
      } else {
        out.push({
          title: `${name} has had no consistent effect on rain here`,
          trigger: `${now}. Of ${im.n} past ${name} seasons here, ${im.drier} were drier and ${im.wetter} wetter than normal (median ${Math.round(im.medianRainPct) > 0 ? "+" : ""}${Math.round(im.medianRainPct)}%).`,
          action: "Plan for the normal range of rainfall and follow the 15-day and monthly forecasts.",
          source: "ERA5 rainfall by NOAA CPC ENSO episode (this page)",
        });
      }
      if (x.heatC != null && im.n >= 5 && im.medianTempAnom >= 0.3 && im.pTemp < 0.05) {
        out.push({
          title: `${name} seasons have been hotter here`,
          trigger: `Past ${name} seasons were a median ${im.medianTempAnom.toFixed(1)} °C warmer than the long-term trend (daily maximum), a consistent difference from neutral seasons.`,
          action: `Heat above ${x.heatC} °C at flowering reduces ${x.cropLabel.toLowerCase()} yield. Do not let the crop run short of water around flowering.`,
          source: x.heatRef ? x.references[x.heatRef] ?? x.heatRef : "",
        });
      }
    }
  }
  return out;
}
