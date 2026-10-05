// Plans which short date windows of the 1991-2020 record are needed for a view,
// so the browser downloads only those instead of 30 full years.
import { Day, daysInMonth, ymd } from "../lib/dates";
import { Calendar, seasonForYear, seasonStatus } from "./season";
import { CLIM_END, CLIM_START } from "./climate";
import { WINDOW_AFTER, WINDOW_BEFORE } from "./onset";

const MS = 86_400_000;

/** Same calendar day `dy` years later (29 Feb -> 28 Feb). */
export function shiftYears(day: Day, dy: number): Day {
  const { y, m, d } = ymd(day);
  const yy = y + dy;
  return Math.round(Date.UTC(yy, m - 1, Math.min(d, daysInMonth(yy, m))) / MS);
}

/** Copy a window into every reference year, clipped to 1991-2020. */
function everyYear([a, b]: [Day, Day]): [Day, Day][] {
  const lo = Math.round(Date.UTC(CLIM_START, 0, 1) / MS);
  const hi = Math.round(Date.UTC(CLIM_END, 11, 31) / MS);
  const y0 = ymd(a).y;
  const out: [Day, Day][] = [];
  for (let y = CLIM_START - 1; y <= CLIM_END; y++) {
    const w: [Day, Day] = [Math.max(lo, shiftYears(a, y - y0)), Math.min(hi, shiftYears(b, y - y0))];
    if (w[1] >= w[0]) out.push(w);
  }
  return out;
}

function monthStart(day: Day): Day { const { y, m } = ymd(day); return Math.round(Date.UTC(y, m - 1, 1) / MS); }
function monthEnd(day: Day): Day { const { y, m } = ymd(day); return Math.round(Date.UTC(y, m - 1, daysInMonth(y, m)) / MS); }

export interface ClimPlan {
  /** rainfall and maximum temperature */
  rainHeat: [Day, Day][];
  /** soil moisture, humidity, ET0 */
  soilAir: [Day, Day][];
}

/**
 * Windows needed by the report:
 *  - each 1991-2020 crop season (+/- 8 days for the +/-7-day bands), for the
 *    rain-since-sowing band, temperature band and hot-day counts;
 *  - the 90 days before the view date (+/- 8), for soil/air bands and percentiles
 *    and, without a crop calendar, recent rain and temperature;
 *  - for a past date, the following ~7 full months, for "what happened next";
 *  - for the current date, the next ~3 weeks of each reference year, for the forecast normal.
 */
export function planClimatology(cal: Calendar | null, asOf: Day, past: boolean): ClimPlan {
  const rainHeat: [Day, Day][] = [];
  if (cal) {
    for (let y = CLIM_START - 1; y <= CLIM_END; y++) {
      const s = seasonForYear(cal, y);
      // from 61 days before sowing (rainy-season onset search) to the harvest
      rainHeat.push([s.plant - WINDOW_BEFORE - 1, Math.max(s.harvest + 8, s.plant + WINDOW_AFTER + 33)]);
    }
  } else {
    rainHeat.push(...everyYear([asOf - 128, asOf + 8]));
  }
  if (past) rainHeat.push(...everyYear([monthStart(asOf) - 8, monthEnd(asOf + 214) + 8]));
  // In current mode, rain and heat for the next ~3 weeks of each reference year,
  // so the 15-day forecast can be compared with the same dates in 1991-2020.
  // Inside a crop season these days are already covered and merge away.
  // Off season, these are needed only when sowing is near (each extra window is
  // one more request against the hourly limit).
  const near = !cal || (() => { const st = seasonStatus(cal, asOf); return st.kind === "in" || st.next.plant - asOf <= 45; })();
  if (!past && near) rainHeat.push(...everyYear([asOf, asOf + 24]));
  const soilAir = everyYear([asOf - 97, asOf + 8]);
  const lo = Math.round(Date.UTC(CLIM_START, 0, 1) / MS);
  const hi = Math.round(Date.UTC(CLIM_END, 11, 31) / MS);
  const clip = (ws: [Day, Day][]) => ws.map(([a, b]) => [Math.max(lo, a), Math.min(hi, b)] as [Day, Day]).filter(([a, b]) => b >= a);
  return { rainHeat: clip(rainHeat), soilAir: clip(soilAir) };
}
