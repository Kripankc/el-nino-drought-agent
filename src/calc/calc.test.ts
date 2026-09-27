// Unit tests for the calculation layer. Inputs are small synthetic series built
// here for testing only; nothing from this file is shown in the app.
import { describe, expect, it } from "vitest";
import { fromDay, toDay, dayOfYear } from "../lib/dates";
import { detrend, permutationTest, percentileRank, quantile } from "./stats";
import { effectiveRain, kcOnDay, seasonForYear, seasonLength, seasonStatus, stagePlan } from "./season";
import { Daily, cumulative, cumulativeRainBand, monthlyVsNormal, seasonTotals, waterBalance } from "./climate";
import { EnsoData, composite, episodeMonths, seasonPhase } from "./enso";

function constDaily(from: string, to: string, v: Partial<Record<keyof Daily, number>>): Daily {
  const a = toDay(from);
  const b = toDay(to);
  const d: Daily = { day: [], precip: [], tmax: [], tmin: [], et0: [], rh: [], sm: [] };
  for (let x = a; x <= b; x++) {
    d.day.push(x);
    d.precip.push(v.precip ?? 0); d.tmax.push(v.tmax ?? 30); d.tmin.push(v.tmin ?? 20);
    d.et0.push(v.et0 ?? 5); d.rh.push(v.rh ?? 60); d.sm.push(v.sm ?? 0.3);
  }
  return d;
}

describe("dates", () => {
  it("round-trips and computes day of year", () => {
    expect(fromDay(toDay("2024-02-29"))).toBe("2024-02-29");
    expect(dayOfYear(toDay("2024-12-31"))).toBe(366);
    expect(dayOfYear(toDay("2023-03-01"))).toBe(60);
  });
});

describe("stats", () => {
  it("quantile matches numpy type 7", () => {
    expect(quantile([1, 2, 3, 4], 0.1)).toBeCloseTo(1.3, 10);
    expect(quantile([5, 1, 3], 0.5)).toBe(3);
  });
  it("percentile rank uses mid-rank for ties", () => {
    expect(percentileRank([1, 2, 3, 4], 2)).toBe(37.5);
  });
  it("detrend removes a linear trend", () => {
    const r = detrend([0, 1, 2, 3], [1, 3, 5, 7]);
    r.forEach((x) => expect(Math.abs(x)).toBeLessThan(1e-12));
  });
  it("permutation test separates distinct groups and not identical ones", () => {
    expect(permutationTest([10, 11, 12, 13, 14], [0, 1, 2, 3, 4], 2000)).toBeLessThan(0.02);
    expect(permutationTest([1, 2, 3, 4], [1, 2, 3, 4], 2000)).toBeGreaterThan(0.5);
  });
});

describe("season", () => {
  const cal = { plantDoy: 305, maturityDoy: 120 }; // Nov -> Apr, wraps the year
  it("handles wrap-around seasons", () => {
    expect(seasonLength(cal)).toBe(180);
    const st = seasonStatus(cal, toDay("2024-01-15"));
    expect(st.kind).toBe("in");
    if (st.kind === "in") expect(st.season.year).toBe(2023);
  });
  it("reports last and next season when off-season", () => {
    const st = seasonStatus(cal, toDay("2024-07-01"));
    expect(st.kind).toBe("off");
    if (st.kind === "off") {
      expect(st.last.year).toBe(2023);
      expect(st.next.year).toBe(2024);
    }
  });
  it("scales FAO-56 stages and builds the Kc curve", () => {
    const plan = stagePlan([30, 40, 50, 30], 150);
    expect(plan.bounds).toEqual([30, 70, 120, 150]);
    const kc: [number, number, number] = [0.3, 1.2, 0.6];
    expect(kcOnDay(kc, plan, 10)).toBe(0.3);
    expect(kcOnDay(kc, plan, 50)).toBeCloseTo(0.3 + (20 / 40) * 0.9, 10);
    expect(kcOnDay(kc, plan, 100)).toBe(1.2);
    expect(kcOnDay(kc, plan, 150)).toBeCloseTo(0.6, 10);
  });
  it("applies the USDA-SCS effective rainfall formula", () => {
    expect(effectiveRain(100)).toBeCloseTo(84, 10);
    expect(effectiveRain(300)).toBeCloseTo(155, 10);
    expect(effectiveRain(50, 15.2)).toBeCloseTo(effectiveRain(100) / 2, 10);
  });
});

describe("climate", () => {
  it("cumulative stops at the first gap", () => {
    const d = constDaily("2020-01-01", "2020-01-05", { precip: 2 });
    d.precip[2] = null;
    expect(cumulative(d, "precip", toDay("2020-01-01"), 5)).toEqual([2, 4, null, null, null]);
  });
  it("water balance: ETc = Kc x ET0 and the gap uses effective rain", () => {
    const d = constDaily("2021-01-01", "2021-12-31", { precip: 0, et0: 4 });
    const s = seasonForYear({ plantDoy: 91, maturityDoy: 241 }, 2021); // 150 days
    const wb = waterBalance(d, s, {
      kc: [1, 1, 1], stages: [30, 40, 50, 30], heat_c: null, heat_ref: null, kc_range: "", stage_row: null,
    }, s.harvest)!;
    expect(wb.totals.etc).toBeCloseTo(4 * 151, 6);
    expect(wb.totals.gap).toBeCloseTo(4 * 151, 6);
    expect(wb.cumRain.at(-1)).toBe(0);
  });
  it("climatological cumulative band only uses complete 1991-2020 seasons", () => {
    const clim = constDaily("1991-01-01", "2020-12-31", { precip: 1 });
    const cal = { plantDoy: 305, maturityDoy: 120 };
    const { years, bands } = cumulativeRainBand(clim, (y) => seasonForYear(cal, y), 180);
    expect(years[0]).toBe(1991);
    expect(years.at(-1)).toBe(2019);
    expect(bands[179].p50).toBe(180);
  });
  it("season totals and monthly anomalies", () => {
    const clim = constDaily("1991-01-01", "2020-12-31", { precip: 1 });
    const obs = constDaily("2023-01-01", "2023-03-15", { precip: 2 });
    const m = monthlyVsNormal(obs, clim, toDay("2023-01-01"), toDay("2023-03-15"));
    expect(m.map((x) => x.m)).toEqual([1, 2]);        // March incomplete -> dropped
    expect(m[0].pct).toBeCloseTo(100, 6);
    const t = seasonTotals(clim, (y) => seasonForYear({ plantDoy: 1, maturityDoy: 10 }, y), 1991, 1992);
    expect(t[0].rain).toBe(10);
    expect(t[0].tmean).toBe(25);
  });
});

describe("enso composites", () => {
  const enso: EnsoData = {
    generated_utc: "", index: "RONI", index_source: "", definition: "", start: "1950-01", values: [],
    episodes: [{ type: "El Nino", start: "1997-05", end: "1998-05", peak: 2.4 }],
    run_in_progress: null, latest: { month: "", value: null }, seas5_nino34: null,
  };
  it("classifies a season by majority of days in an episode", () => {
    const months = episodeMonths(enso);
    expect(months.get("1997-12")).toBe("El Nino");
    expect(seasonPhase(months, seasonForYear({ plantDoy: 305, maturityDoy: 120 }, 1997))).toBe("El Nino");
    expect(seasonPhase(months, seasonForYear({ plantDoy: 305, maturityDoy: 120 }, 1995))).toBe("Neutral");
  });
  it("computes rainfall departures against the 1991-2020 normal", () => {
    const totals = Array.from({ length: 40 }, (_, k) => ({
      year: 1981 + k, rain: 1981 + k === 1997 ? 50 : 100, tmean: 25,
    }));
    const c = composite(totals, (y) => seasonForYear({ plantDoy: 305, maturityDoy: 120 }, y), enso)!;
    const p97 = c.points.find((p) => p.year === 1997)!;
    expect(p97.phase).toBe("El Nino");
    expect(c.byPhase["El Nino"].n).toBe(1);
    expect(p97.rainPct).toBeLessThan(-45);
  });
});
