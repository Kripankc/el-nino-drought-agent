// Rainy-season onset ("when is it safe to sow?").
// Definition (Sivakumar 1988, Agric. For. Meteorol. 42:295-305; used by FAO and
// many national met services): the first day, from the start of the search
// window, on which at least 20 mm of rain falls over 3 consecutive days, with
// no dry spell of 7 or more consecutive days (each < 1 mm) in the following 30 days.
// A "false start" is a 20 mm/3-day rain followed by such a dry spell.
import { Day } from "../lib/dates";
import { Daily, indexOf } from "./climate";
import { Season } from "./season";
import { quantile } from "./stats";

export const ONSET_RAIN = 20;   // mm over 3 days
export const DRY_DAY = 1;       // mm
export const DRY_SPELL = 7;     // days
export const LOOKAHEAD = 30;    // days after the wet spell
export const WINDOW_BEFORE = 60; // search from 60 days before the usual sowing date
export const WINDOW_AFTER = 60;  // ... to 60 days after

export interface OnsetYear {
  year: number;
  onset: number | null;      // days relative to the usual sowing date (negative = earlier)
  falseStart: boolean;       // the first 20 mm/3-day rain was followed by a 7-day dry spell
  complete: boolean;         // all data needed was present
}

/** Onset in one window. `get(day)` returns rain or null. Returns days from `start`, or null. */
function onsetIn(get: (d: Day) => number | null, start: Day, end: Day): { onset: number | null; falseStart: boolean; complete: boolean } {
  let firstWet: boolean | null = null; // was the first wet spell a false start?
  for (let d = start; d <= end; d++) {
    const r = [0, 1, 2].map((k) => get(d + k));
    if (r.some((x) => x == null)) return { onset: null, falseStart: false, complete: false };
    if ((r[0]! + r[1]! + r[2]!) < ONSET_RAIN) continue;
    // look for a dry spell in the 30 days after the wet spell
    let run = 0;
    let dry = false;
    for (let k = 3; k < 3 + LOOKAHEAD; k++) {
      const x = get(d + k);
      if (x == null) return { onset: null, falseStart: false, complete: false };
      run = x < DRY_DAY ? run + 1 : 0;
      if (run >= DRY_SPELL) { dry = true; break; }
    }
    if (firstWet == null) firstWet = dry;
    if (!dry) return { onset: d - start, falseStart: firstWet, complete: true };
  }
  return { onset: null, falseStart: firstWet === true, complete: true };
}

/** Onset for each year whose season is given, relative to that year's usual sowing date. */
export function onsetYears(data: Daily, seasonFor: (y: number) => Season, years: number[]): OnsetYear[] {
  const ix = indexOf(data);
  const get = (d: Day) => { const i = ix.get(d); return i === undefined ? null : data.precip[i]; };
  return years.map((year) => {
    const plant = seasonFor(year).plant;
    const r = onsetIn(get, plant - WINDOW_BEFORE, plant + WINDOW_AFTER);
    return { year, onset: r.onset == null ? null : r.onset - WINDOW_BEFORE, falseStart: r.falseStart, complete: r.complete };
  });
}

/**
 * This season so far, using data up to `until`: a confirmed onset, a possible
 * one still inside its 30-day check, or neither. Days are relative to sowing.
 */
export function onsetSoFar(data: Daily, plant: Day, until: Day): { onset: number | null; pending: number | null; pendingCheckEnd: Day | null } {
  const ix = indexOf(data);
  const get = (d: Day) => { if (d > until) return null; const i = ix.get(d); return i === undefined ? null : data.precip[i]; };
  for (let d = plant - WINDOW_BEFORE; d + 2 <= until && d <= plant + WINDOW_AFTER; d++) {
    const r = [0, 1, 2].map((k) => get(d + k));
    if (r.some((x) => x == null)) return { onset: null, pending: null, pendingCheckEnd: null };
    if (r[0]! + r[1]! + r[2]! < ONSET_RAIN) continue;
    let run = 0;
    let dry = false;
    let k = 3;
    for (; k < 3 + LOOKAHEAD && d + k <= until; k++) {
      const x = get(d + k)!;
      run = x < DRY_DAY ? run + 1 : 0;
      if (run >= DRY_SPELL) { dry = true; break; }
    }
    if (dry) continue;                                   // false start
    if (k >= 3 + LOOKAHEAD) return { onset: d - plant, pending: null, pendingCheckEnd: null };
    return { onset: null, pending: d - plant, pendingCheckEnd: d + 2 + LOOKAHEAD };
  }
  return { onset: null, pending: null, pendingCheckEnd: null };
}

export interface OnsetSummary {
  n: number;                    // years with complete data
  found: number;                // years with an onset inside the window
  byDay: { day: number; pct: number }[]; // % of years started by each day (relative to sowing)
  p80: number | null;           // day by which 80% of years had started
  median: number | null;
  falseStartPct: number;
  /** Onset found in the first 5 days of the window in most years: rain is not limiting */
  alwaysWet: boolean;
}

export function summarise(ys: OnsetYear[]): OnsetSummary {
  const ok = ys.filter((y) => y.complete);
  const n = ok.length;
  const days = ok.map((y) => y.onset).filter((x): x is number => x != null).sort((a, b) => a - b);
  const byDay: { day: number; pct: number }[] = [];
  for (let d = -WINDOW_BEFORE; d <= WINDOW_AFTER; d++) byDay.push({ day: d, pct: n ? (100 * days.filter((x) => x <= d).length) / n : 0 });
  // p80 counts years without onset in the window as "later than the window"
  const need = Math.ceil(0.8 * n);
  return {
    n,
    found: days.length,
    byDay,
    p80: n && days.length >= need ? days[need - 1] : null,
    median: days.length * 2 >= n && n ? days[Math.ceil(n / 2) - 1] : null,
    falseStartPct: n ? (100 * ok.filter((y) => y.falseStart).length) / n : 0,
    alwaysWet: n > 0 && days.filter((x) => x <= -WINDOW_BEFORE + 5).length >= 0.8 * n,
  };
}

/** Median shift (days) of one set of onsets against another, both with at least 5 found. */
export function medianShift(a: OnsetYear[], b: OnsetYear[]): number | null {
  const da = a.map((y) => y.onset).filter((x): x is number => x != null);
  const db = b.map((y) => y.onset).filter((x): x is number => x != null);
  if (da.length < 5 || db.length < 5) return null;
  return Math.round(quantile(da, 0.5) - quantile(db, 0.5));
}
