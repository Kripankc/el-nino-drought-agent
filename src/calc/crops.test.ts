import { describe, expect, it } from "vitest";
import { toDay } from "../lib/dates";
import { cropChoices } from "./crops";
import { LANGS, localize, langForCountry } from "../i18n/advice";
import type { Advice } from "./advice";

describe("crop choices", () => {
  const crops = [
    { ha: 6000, share: 0.6, ggcmi: ["ri1", "ri2"] },
    { ha: 3000, share: 0.3, ggcmi: ["wwh", "swh"] },
    { ha: 100, share: 0.01, ggcmi: ["soy"] },
  ];
  const cal: Record<string, [number, number]> = {
    ri1_rf: [181, 288], ri1_ir: [175, 290], wwh_rf: [314, 105], soy_rf: [160, 280], mai_rf: [100, 200],
  };
  it("offers only crops mapped in the cell, largest first, rainfed first", () => {
    const { options } = cropChoices(crops, cal, toDay("2026-08-01"));
    expect(options.map((o) => o.key)).toEqual(["ri1_rf", "ri1_ir", "wwh_rf"]);
  });
  it("defaults to the crop in season on the date", () => {
    expect(cropChoices(crops, cal, toDay("2026-08-01")).pick).toBe("ri1_rf");
    expect(cropChoices(crops, cal, toDay("2027-01-15")).pick).toBe("wwh_rf");
  });
  it("falls back to the next crop sown when none is in season", () => {
    expect(cropChoices(crops, cal, toDay("2026-10-25")).pick).toBe("wwh_rf");
  });
});

describe("advice translations", () => {
  const base = { phase: "El Nino", status: "developing", n: 12, k: 8, median: -14, clear: false, drier: 8, wetter: 4 };
  const items: Advice[] = [
    { id: "rain_low", v: { pct: 12, gap: 40, mid0: toDay("2026-08-01"), mid1: toDay("2026-09-01") }, source: "" },
    { id: "soil_dry", v: { pct: 5 }, source: "" },
    { id: "heat_mid", v: { hot: 3, n: 15, thr: 35 }, source: "" },
    { id: "heavy_rain", v: { mm: 90, start: toDay("2026-10-07") }, source: "" },
    { id: "seas_dry", v: { months: [11, 12], inSeason: true }, source: "" },
    { id: "seas_wet", v: { months: [1] }, source: "" },
    { id: "dry_fortnight", v: { total: 4, normal: 30, drierThan: 90, inSeason: false }, source: "" },
    { id: "enso_pending", v: { phase: "La Nina", status: "expected", loading: true }, source: "" },
    { id: "enso_dry_pre", v: base, source: "" },
    { id: "enso_dry_in", v: { ...base, soFar: 22, mid0: null, mid1: null, hasPlan: false }, source: "" },
    { id: "enso_wet", v: { ...base, k: 7 }, source: "" },
    { id: "enso_none", v: base, source: "" },
    { id: "enso_hot", v: { phase: "El Nino", status: "active", tAnom: 0.6, thr: 35 }, source: "" },
  ];
  it("renders every message in every language without gaps", () => {
    for (const l of LANGS) for (const a of items) {
      const t = localize(a, l.id);
      for (const s of [t.title, t.action, t.trigger]) {
        expect(s.length).toBeGreaterThan(5);
        expect(s).not.toMatch(/undefined|NaN|null|\[object/);
      }
    }
  });
  it("picks the language from the country", () => {
    expect(langForCountry("NP")).toBe("ne");
    expect(langForCountry("br")).toBe("pt");
    expect(langForCountry("de")).toBe("en");
    expect(langForCountry(null)).toBe("en");
  });
});
