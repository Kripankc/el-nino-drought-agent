import { describe, expect, it } from "vitest";
import { fromDay, toDay } from "../lib/dates";
import { planClimatology, shiftYears } from "./windows";
import { mergeDaily, mergeWindows, requestWeight } from "../api/openmeteo";

const weightOf = (ws: [number, number][], vars: number) =>
  ws.reduce((a, [s, e]) => a + Math.max(1, ((e - s + 1) / 14) * (vars / 10)), 0);

describe("climatology windows", () => {
  it("shifts dates by whole years and clamps 29 Feb", () => {
    expect(fromDay(shiftYears(toDay("2024-02-29"), -1))).toBe("2023-02-28");
    expect(fromDay(shiftYears(toDay("2026-09-21"), -30))).toBe("1996-09-21");
  });
  it("covers every 1991-2020 season and stays inside the reference period", () => {
    const p = planClimatology({ plantDoy: 320, maturityDoy: 134 }, toDay("2026-09-21"), false);
    const all = [...p.rainHeat, ...p.soilAir];
    expect(Math.min(...all.map((w) => w[0]))).toBeGreaterThanOrEqual(toDay("1991-01-01"));
    expect(Math.max(...all.map((w) => w[1]))).toBeLessThanOrEqual(toDay("2020-12-31"));
    expect(p.rainHeat.length).toBeGreaterThanOrEqual(30);
    expect(p.soilAir.length).toBe(30);
  });
  it("reaches three weeks ahead in current mode only", () => {
    const asOf = toDay("2026-09-21");
    const now = planClimatology(null, asOf, false);
    const past = planClimatology(null, asOf, true);
    expect(fromDay(Math.max(...now.rainHeat.map((w) => w[1])))).toBe("2020-10-15");
    expect(fromDay(Math.max(...past.rainHeat.map((w) => w[1])))).not.toBe("2020-10-15");
  });
  it("costs far less than downloading 30 full years", () => {
    const p = planClimatology({ plantDoy: 320, maturityDoy: 134 }, toDay("2026-09-21"), false);
    const planned = weightOf(mergeWindows(p.rainHeat), 2) + weightOf(mergeWindows(p.soilAir), 3) + 1;
    const fullYears = (10958 / 14) * (5 / 10);
    expect(planned).toBeLessThan(fullYears / 2);
    expect(planned).toBeLessThan(200);
  });
});

describe("request helpers", () => {
  it("estimates Open-Meteo request weight like the server", () => {
    const u = "https://archive-api.open-meteo.com/v1/archive?latitude=1&longitude=2&start_date=1991-01-01&end_date=2020-12-31&daily=a,b,c,d,e";
    expect(requestWeight(u)).toBeCloseTo((10958 / 14) * 0.5, 6);
    expect(requestWeight("https://x.org/v1/archive?latitude=1&longitude=2&start_date=2020-01-01&end_date=2020-01-05&daily=a")).toBe(1);
  });
  it("merges windows and daily parts field by field", () => {
    expect(mergeWindows([[5, 9], [1, 3], [4, 4], [20, 25]])).toEqual([[1, 9], [20, 25]]);
    const a = { day: [1, 2], precip: [1, 2], tmax: [30, 31], tmin: [null, null], et0: [null, null], rh: [null, null], sm: [null, null] };
    const b = { day: [2, 3], precip: [null, null], tmax: [null, null], tmin: [null, null], et0: [4, 5], rh: [60, 61], sm: [0.2, 0.3] };
    const m = mergeDaily([a, b]);
    expect(m.day).toEqual([1, 2, 3]);
    expect(m.precip).toEqual([1, 2, null]);
    expect(m.et0).toEqual([null, 4, 5]);
  });
});
