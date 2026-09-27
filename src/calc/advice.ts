// Rule-based guidance. Every item states the trigger (the data that fired it)
// and the source of the agronomic statement. Nothing fires without data.
import { Day, fmtDay, monthName, toDay } from "../lib/dates";
import { Season, StagePlan } from "./season";
import { median } from "./stats";
import type { Composite } from "./enso";
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
  composite: Composite | null;
  ensoNow: { type: string; seasons_so_far: number } | null;
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
  if (x.seasonal && mid) {
    const dryMonths = x.seasonal.filter((m) => {
      const start = toDay(m.month + "-01");
      return start <= mid[1] && start + 30 >= mid[0] && m.precipPct != null && m.precipPct <= -20;
    });
    if (dryMonths.length) {
      const names = dryMonths.map((m) => monthName(Number(m.month.slice(5, 7)))).join(", ");
      out.push({
        title: "Seasonal forecast leans dry for the sensitive stage",
        trigger: `ECMWF SEAS5 ensemble-mean rainfall for ${names} is at least 20% below the model's own normal.`,
        action: x.inSeason
          ? "Plan now for supplementary irrigation or water harvesting around flowering, and keep soil cover to hold moisture."
          : "If you have not sown yet, discuss shorter-duration or drought-tolerant varieties with your extension office.",
        source: `${fao33}; seasonal forecasts have limited skill at a single location`,
      });
    }
  }

  // 6. El Nino currently active and historically dry here
  if (x.composite && x.ensoNow?.type === "El Nino") {
    const c = x.composite;
    const n = c.byPhase["El Nino"];
    if (c.pRainNinoVsNeutral < 0.05 && n.medianRainPct < 0) {
      out.push({
        title: "El Niño seasons have been dry here",
        trigger: `El Niño conditions are present (${x.ensoNow.seasons_so_far} consecutive seasons at or above +0.5 °C). In ${n.drierCount} of ${n.n} past El Niño seasons, rainfall for this crop season was below the 1991–2020 normal (median ${Math.round(n.medianRainPct)}%).`,
        action: "Treat a below-normal season as more likely than usual when planning seed, water and inputs.",
        source: "ERA5 rainfall composites by NOAA CPC ENSO episode (this page)",
      });
    }
  }
  return out;
}
