import { describe, expect, it } from "vitest";
import { toDay } from "../lib/dates";
import { Daily } from "./climate";
import { seasonForYear } from "./season";
import { medianShift, onsetSoFar, onsetYears, summarise } from "./onset";

// Synthetic rain only, for testing the onset rule.
function series(from: string, to: string, rain: (d: number) => number): Daily {
  const a = toDay(from), b = toDay(to);
  const d: Daily = { day: [], precip: [], tmax: [], tmin: [], et0: [], rh: [], sm: [] };
  for (let x = a; x <= b; x++) { d.day.push(x); d.precip.push(rain(x)); d.tmax.push(null); d.tmin.push(null); d.et0.push(null); d.rh.push(null); d.sm.push(null); }
  return d;
}
const cal = { plantDoy: 166, maturityDoy: 288 };  // sow ~15 Jun
const seasonFor = (y: number) => seasonForYear(cal, y);

describe("rainy-season onset", () => {
  it("finds the first 20 mm/3-day rain not followed by a 7-day dry spell", () => {
    const plant = seasonFor(2000).plant;
    // false start 20 days before sowing (25 mm then 10 dry days), real start 5 days after sowing
    const data = series("2000-01-01", "2000-12-31", (x) => {
      if (x === plant - 20) return 25;
      if (x > plant - 20 && x < plant - 10) return 0;
      if (x >= plant + 5) return 8;
      return 0.2;
    });
    const [y] = onsetYears(data, seasonFor, [2000]);
    expect(y.onset).toBe(5);
    expect(y.falseStart).toBe(true);
    expect(y.complete).toBe(true);
  });
  it("reports no onset when the window stays dry, and incomplete when data are missing", () => {
    const dry = series("2001-01-01", "2001-12-31", () => 0);
    expect(onsetYears(dry, seasonFor, [2001])[0]).toMatchObject({ onset: null, complete: true });
    expect(onsetYears(dry, seasonFor, [2002])[0].complete).toBe(false);
  });
  it("summarises the share of years started by each day", () => {
    const ys = Array.from({ length: 10 }, (_, k) => ({ year: 1990 + k, onset: k * 3 - 10, falseStart: k < 2, complete: true }));
    const s = summarise(ys);
    expect(s.n).toBe(10);
    expect(s.p80).toBe(11);              // 8th earliest of -10..17 step 3
    expect(s.falseStartPct).toBe(20);
    expect(s.byDay.find((d) => d.day === 0)!.pct).toBe(40);
    expect(medianShift(ys.map((y) => ({ ...y, onset: y.onset! + 10 })), ys)).toBe(10);
  });
  it("tells a confirmed start from one still being checked", () => {
    const plant = seasonFor(2026).plant;
    const data = series("2026-03-01", "2026-09-30", (x) => (x >= plant ? 8 : 0));
    expect(onsetSoFar(data, plant, plant + 40).onset).toBe(0);
    const early = onsetSoFar(data, plant, plant + 10);
    expect(early.onset).toBeNull();
    expect(early.pending).toBe(0);
  });
});
