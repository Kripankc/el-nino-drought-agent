import { Day, dayOfYear, fmtDay, fromDay, monthName, toDate, toDay, todayDay, ymd } from "../lib/dates";
import { CropParamFile, LocalCrops } from "../api/static";
import { EnsembleDay, GridInfo, SeasonalMonth, era5Daily, ensembleForecast, lastEra5Day, mergeDaily, seasonalMonthly } from "../api/openmeteo";
import {
  Band, Daily, cumulative, cumulativeRainBand, doyBands, doyPercentile, hotDayCounts, indexOf,
  monthlyVsNormal, seasonTotals, waterBalance,
} from "../calc/climate";
import { Calendar, CropParams, STAGE_NAMES, Season, seasonForYear, seasonStatus, stageIndex, stagePlan, StagePlan } from "../calc/season";
import { Composite, EnsoData, composite, episodeMonths, indexValue, seasonPhase } from "../calc/enso";
import { finite, median, percentileRank, quantile } from "../calc/stats";
import { Advice, buildAdvice } from "../calc/advice";
import { S } from "../strings";
import { block, chart, el, fmt, note, resetCharts, stat } from "./dom";
import { anomalyBars, compositeDots, ensoTimeline, forecastRain, legend, r1, tableView, theme, timeChart } from "./charts";
import type { State } from "../main";

export interface RenderCtx {
  root: HTMLElement;
  state: State;
  params: CropParamFile;
  enso: EnsoData | null;
  local: LocalCrops;
  cropsLoaded: boolean;
  cropKey: string | null;
  cal: Calendar | null;
  clim: Daily;
  grid: GridInfo;
  alive: () => boolean;
  setStatus: (m: string, err?: boolean) => void;
}

const MIN_CROPLAND_HA = 50;
const src = (t: string) => note(t, "src");

export async function renderReport(c: RenderCtx) {
  resetCharts();
  c.root.replaceChildren();
  const today = todayDay();
  const last = lastEra5Day();
  const D = Math.min(c.state.date, today);
  const current = D >= today - 7;
  const asOf = current ? last : D;

  const code = c.cropKey?.slice(0, 3) ?? null;
  const cropLabel = code ? c.params.ggcmi_labels[code] ?? code : "";
  const p: CropParams | null = code ? c.params.params[c.params.ggcmi_to_param[code]] ?? null : null;

  // ---------------------------------------------------------------- header
  const title = el("h2", { id: "place-name" }, c.state.name ?? `${c.state.lat!.toFixed(3)}, ${c.state.lon!.toFixed(3)}`);
  c.root.append(el("section", { class: "block" }, title,
    note(`ERA5 grid cell centre ${c.grid.latitude.toFixed(2)}, ${c.grid.longitude.toFixed(2)} · elevation ${Math.round(c.grid.elevation)} m · ` +
      (current ? `ERA5 observations up to ${fmtDay(last)} (published with about 5 days' delay)` : `showing conditions as of ${fmtDay(D)}`))));
  if (!current) {
    c.root.append(el("div", { class: "banner" },
      `Past date selected (${fmtDay(D)}). Charts show the season around that date. The forecast sections are replaced by what was observed afterwards. No advice is given for past dates.`));
  }

  // ---------------------------------------------------------------- 2. crops here
  const here = block(c.root, S.h.here);
  renderHere(here, c);

  // Season to analyse
  let season: Season | null = null;
  let nextSeason: Season | null = null;
  let inSeason = false;
  let dayOfSeason = 0;
  if (c.cal) {
    const st = seasonStatus(c.cal, asOf);
    if (st.kind === "in") { season = st.season; inSeason = true; dayOfSeason = st.dayOfSeason; nextSeason = seasonForYear(c.cal, st.season.year + 1); }
    else { season = st.last; nextSeason = st.next; }
  }
  const plan: StagePlan | null = season && p?.stages ? stagePlan(p.stages, season.length) : null;

  // ---------------------------------------------------------------- fetch observations
  c.setStatus(S.status.season);
  const from: Day = season ? Math.min(season.plant, asOf - 30) : asOf - 150;
  const to: Day = current ? last : Math.min(last, Math.max(season?.harvest ?? D, D + 214));
  const obs = (await era5Daily(c.state.lat!, c.state.lon!, from, to, ["precip", "tmax", "tmin", "et0", "rh", "sm"], (m) => c.setStatus(m))).data;
  if (!c.alive()) return;
  let cmp: { season: Season; data: Daily } | null = null;
  if (c.cal && c.state.cmp) {
    const cs = seasonForYear(c.cal, c.state.cmp);
    const d = (await era5Daily(c.state.lat!, c.state.lon!, cs.plant, cs.harvest, ["precip", "tmax", "tmin", "et0"])).data;
    cmp = { season: cs, data: d };
    if (!c.alive()) return;
  }

  // ---------------------------------------------------------------- 3. season strip
  if (c.cal && season) {
    const b = block(c.root, S.h.strip);
    renderStrip(b, c, season, nextSeason!, inSeason, dayOfSeason, plan, asOf, cropLabel);
  }

  // ---------------------------------------------------------------- 4. water
  let gapMm: number | null = null;
  let rainPct: number | null = null;
  if (c.cal && season) {
    const b = block(c.root, S.h.water);
    const r = renderWater(b, c, season, obs, asOf, p, cmp, cropLabel);
    gapMm = r.gap; rainPct = r.percentile;
  }

  // ---------------------------------------------------------------- 5. temperature
  const tb = block(c.root, S.h.temp);
  const range: [Day, Day] = season ? [season.plant, Math.min(season.harvest, asOf)] : [asOf - 120, asOf];
  renderTemp(tb, c, obs, range, p, season, cmp, cropLabel);

  // ---------------------------------------------------------------- 6. other
  const ob = block(c.root, S.h.other);
  const smPct = renderOther(ob, c, obs, range, asOf);

  // ---------------------------------------------------------------- 7/8. forecast or what happened next
  let fc: EnsembleDay[] | null = null;
  let seas: SeasonalMonth[] | null = null;
  if (current) {
    c.setStatus(S.status.forecast);
    const fb = block(c.root, S.h.fc);
    const sb = block(c.root, S.h.seas);
    const [f, s] = await Promise.allSettled([
      ensembleForecast(c.state.lat!, c.state.lon!),
      seasonalMonthly(c.state.lat!, c.state.lon!),
    ]);
    if (!c.alive()) return;
    if (f.status === "fulfilled") { fc = f.value.days; renderForecast(fb, c, fc, p); }
    else fb.append(note(`Forecast unavailable: ${(f.reason as Error).message}`, "note error"));
    if (s.status === "fulfilled") { seas = s.value; renderSeasonal(sb, seas, season, nextSeason, inSeason, plan, c.cal ? seasonPlanFor(nextSeason, p) : null); }
    else sb.append(note(`Seasonal forecast unavailable: ${(s.reason as Error).message}`, "note error"));
  } else {
    const ab = block(c.root, S.h.after);
    renderAfter(ab, c, obs, D);
  }

  // ---------------------------------------------------------------- 9. El Nino
  const eb = block(c.root, S.h.enso);
  // ---------------------------------------------------------------- 10. advice
  const adv = current ? block(c.root, S.h.advice) : null;
  const advice = (comp: Composite | null) => {
    if (!adv) return;
    adv.replaceChildren(el("h2", {}, S.h.advice));
    if (!c.cal || !season) {
      adv.append(note("Advice needs a crop calendar, and none is available for this location."));
      return;
    }
    const target = inSeason ? season : nextSeason!;
    const items = buildAdvice({
      cropLabel, season: target, inSeason, today,
      plan: p?.stages ? stagePlan(p.stages, target.length) : null,
      heatC: p?.heat_c ?? null, heatRef: p?.heat_ref ?? null,
      rainPercentile: inSeason ? rainPct : null, gapMm: inSeason ? gapMm : null,
      smPercentile: smPct, forecast: fc, seasonal: seas, composite: comp,
      ensoNow: c.enso?.run_in_progress ?? null, references: c.params.references,
    });
    renderAdvice(adv, items);
  };
  renderEnso(eb, c, D, current, season, (comp) => advice(comp));
  advice(null);

  // ---------------------------------------------------------------- 11. limits
  const lb = block(c.root, S.h.limits);
  lb.append(el("ul", {}, ...S.limits.map((t) => el("li", {}, t))));
}

function seasonPlanFor(s: Season | null, p: CropParams | null): StagePlan | null {
  return s && p?.stages ? stagePlan(p.stages, s.length) : null;
}

// =====================================================================
function renderHere(b: HTMLElement, c: RenderCtx) {
  if (!c.cropsLoaded) {
    b.append(note("The crop map could not be loaded. The data files may not have been built yet (see README: Build the data).", "note error"));
    return;
  }
  const L = c.local;
  if (L.totalHa < MIN_CROPLAND_HA) {
    b.append(el("p", { class: "lead" }, "No cropland is recorded in this cell (about 28 × 28 km) in CROPGRIDS. Weather and climate sections below still apply."));
  } else {
    const pctCell = (100 * L.totalHa) / 100 / L.cellKm2;
    b.append(el("p", { class: "lead" },
      `Harvested crop area in this ~28 km cell is about ${Math.round(L.totalHa).toLocaleString("en")} ha, equal to ${pctCell < 1 ? "<1" : Math.round(pctCell)}% of the cell area (harvested area counts land cropped twice in a year twice).`));
    const t = el("table", { class: "crops" });
    t.append(el("thead", {}, el("tr", {}, el("th", {}, "Crop"), el("th", { class: "num" }, "Harvested area"), el("th", { class: "num" }, "Share"), el("th", {}, "Sowing – maturity"))));
    const tb = el("tbody");
    for (const cr of L.crops) {
      const cals = cr.ggcmi.flatMap((g) => ["rf", "ir"].filter((s) => L.calendars[`${g}_${s}`]).map((s) => `${g}_${s}`));
      const calTxt = cals.length ? cals.map((k) => {
        const [pd, md] = L.calendars[k];
        const sys = k.endsWith("_ir") ? "irrigated" : "rainfed";
        const lab = c.params.ggcmi_labels[k.slice(0, 3)];
        return `${lab} (${sys}): ${doyLabel(pd)} – ${doyLabel(md)}`;
      }).join("; ") : "not in GGCMI";
      tb.append(el("tr", {},
        el("td", {}, cap(cr.name)),
        el("td", { class: "num" }, `${Math.round(cr.ha).toLocaleString("en")} ha`),
        el("td", { class: "num" }, `${Math.round(cr.share * 100)}%`),
        el("td", {}, calTxt)));
    }
    t.append(tb);
    b.append(t);
  }
  const idx = c.params.references;
  void idx;
  b.append(src("CROPGRIDS v1.08, harvested area circa 2020 (Tang et al. 2024), aggregated to 0.25°. Calendars: GGCMI Phase 3 (Jägermeyr et al. 2021), 0.5°."));
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
function doyLabel(doy: number): string {
  const d = toDate(toDay("2001-01-01") + doy - 1);
  return `${d.getUTCDate()} ${monthName(d.getUTCMonth() + 1)}`;
}

// =====================================================================
function renderStrip(b: HTMLElement, c: RenderCtx, season: Season, next: Season, inSeason: boolean, dos: number,
  plan: StagePlan | null, asOf: Day, cropLabel: string) {
  const sys = c.cropKey!.endsWith("_ir") ? "irrigated" : "rainfed";
  if (inSeason) {
    const stage = plan ? STAGE_NAMES[stageIndex(plan, dos)] : null;
    b.append(el("p", { class: "lead" },
      `${cropLabel} (${sys}) is on day ${dos} of about ${season.length}` + (stage ? `, ${stage.toLowerCase()} stage.` : ".") +
      ` Sown about ${fmtDay(season.plant)}, maturity about ${fmtDay(season.harvest)}.`));
  } else {
    b.append(el("p", { class: "lead" },
      `Between seasons. The last ${cropLabel.toLowerCase()} (${sys}) season ran from about ${fmtDay(season.plant)} to ${fmtDay(season.harvest)}. The next is expected to be sown about ${fmtDay(next.plant)} (${next.plant - asOf} days).`));
  }
  const t = theme();
  const H = 70;
  const draw = (W: number) => {
  const x = (d: Day) => ((d - season.plant) / season.length) * (W - 20) + 10;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", String(W));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Crop stages across the season");
  const rect = (x0: number, x1: number, fill: string) => {
    const r = document.createElementNS(svg.namespaceURI, "rect");
    Object.entries({ x: x0 + 1, y: 14, width: Math.max(0, x1 - x0 - 2), height: 22, rx: 4, fill }).forEach(([k, v]) => r.setAttribute(k, String(v)));
    svg.append(r);
  };
  const text = (tx: number, ty: number, s: string, anchor = "middle", fill = t.ink2, size = 12) => {
    const e = document.createElementNS(svg.namespaceURI, "text");
    Object.entries({ x: tx, y: ty, "text-anchor": anchor, fill, "font-size": size }).forEach(([k, v]) => e.setAttribute(k, String(v)));
    e.textContent = s;
    svg.append(e);
  };
  if (plan) {
    let prev = 0;
    plan.bounds.forEach((bd, i) => {
      const x0 = x(season.plant + prev);
      const x1 = x(season.plant + bd);
      rect(x0, x1, i === 2 ? getComputedStyle(document.documentElement).getPropertyValue("--stage-mid").trim() : getComputedStyle(document.documentElement).getPropertyValue("--stage").trim());
      if (x1 - x0 > 78) text((x0 + x1) / 2, 30, STAGE_NAMES[i], "middle", t.ink, 12);
      prev = bd;
    });
  } else {
    rect(x(season.plant), x(season.harvest), getComputedStyle(document.documentElement).getPropertyValue("--stage").trim());
    text(W / 2, 30, "Stage lengths not available for this crop (FAO-56 Table 11)", "middle", t.ink2);
  }
  text(10, 54, `Sow ${fmtDay(season.plant)}`, "start");
  text(W - 10, 54, `Mature ${fmtDay(season.harvest)}`, "end");
  if (inSeason) {
    const xm = x(asOf);
    const l = document.createElementNS(svg.namespaceURI, "line");
    Object.entries({ x1: xm, x2: xm, y1: 6, y2: 42, stroke: t.ink, "stroke-width": 2 }).forEach(([k, v]) => l.setAttribute(k, String(v)));
    svg.append(l);
    text(xm, 66, "today", "middle", t.ink, 12);
  }
  return svg;
  };
  chart(b, (w) => draw(w));
  if (plan) b.append(note("Mid-season (shaded) covers flowering and grain or yield formation for most crops; water shortage in this stage costs the most yield (FAO-33)."));
  b.append(src(`GGCMI Phase 3 sowing and maturity dates; stage proportions from FAO-56 Table 11 (${c.params.params[c.params.ggcmi_to_param[c.cropKey!.slice(0, 3)]]?.stage_row ?? "n/a"}), scaled to the local season length.`));
}

// =====================================================================
function renderWater(b: HTMLElement, c: RenderCtx, season: Season, obs: Daily, asOf: Day, p: CropParams | null,
  cmp: { season: Season; data: Daily } | null, cropLabel: string): { gap: number | null; percentile: number | null } {
  const L = season.length + 1;
  const { bands, curves, years } = cumulativeRainBand(c.clim, (y) => seasonForYear(c.cal!, y), L);
  const cumR = cumulative(obs, "precip", season.plant, L);
  const wb = p ? waterBalance(obs, season, p, asOf) : null;

  let k = -1;
  cumR.forEach((v, i) => { if (v != null && season.plant + i <= asOf) k = i; });
  const done = season.harvest <= asOf;
  let percentile: number | null = null;
  if (k >= 0 && curves.length >= 10) percentile = percentileRank(curves.map((cv) => cv[k]), cumR[k]!);

  // Headline
  if (k >= 0) {
    const normal = bands[k]?.p50;
    const pctOfNormal = normal > 0 ? (100 * cumR[k]!) / normal : null;
    b.append(el("p", { class: "lead" },
      `${done ? "Season total" : "Rain since sowing"}: ${fmt.mm(cumR[k]!)}` +
      (pctOfNormal != null ? `, ${Math.round(pctOfNormal)}% of the 1991–2020 median for the same days` : "") +
      (percentile != null ? ` (${fmt.ord(percentile)} percentile).` : ".")));
  }
  const stats = el("div", { class: "stats" });
  if (k >= 0) stats.append(stat(fmt.mm(cumR[k]!), `rain, ${fmtDay(season.plant)} – ${fmtDay(season.plant + k)}`));
  if (k >= 0 && bands[k]) stats.append(stat(`${fmt.mm(bands[k].p10)} – ${fmt.mm(bands[k].p90)}`, "normal range for the same days (10th–90th percentile, 1991–2020)"));
  if (wb) {
    stats.append(stat(fmt.mm(wb.totals.etc), `${cropLabel} water need (ETc) so far`));
    stats.append(stat(fmt.mm(wb.totals.gap), "shortfall after effective rain (irrigation need)"));
  }
  b.append(stats);

  const T = theme();
  const bandPts = bands.map((bd: Band, i) => ({ day: season.plant + i, lo: bd.p10, mid: bd.p50, hi: bd.p90 }));
  const lines = [{ label: "This season", color: T.this, points: cumR.map((y, i) => ({ day: season.plant + i, y: season.plant + i <= asOf ? y : null })) }];
  if (wb) lines.push({ label: `${cropLabel} water need`, color: T.need, points: wb.cumEtc.map((y, i) => ({ day: season.plant + i, y })) });
  if (cmp) {
    const cc = cumulative(cmp.data, "precip", cmp.season.plant, L);
    lines.push({ label: `Season ${cmp.season.year}`, color: T.cmp, points: cc.map((y, i) => ({ day: season.plant + i, y })) });
  }
  b.append(legend([
    { label: "This season", color: T.this, kind: "line" },
    ...(wb ? [{ label: "Crop water need (FAO-56 ETc, cumulative)", color: T.need, kind: "line" as const }] : []),
    ...(cmp ? [{ label: `Season ${cmp.season.year} (same days after sowing)`, color: T.cmp, kind: "line" as const }] : []),
    { label: `Normal range 1991–2020 (10th–90th percentile, ${years.length} seasons)`, color: T.band, kind: "band" },
  ]));
  chart(b, (w) => timeChart({
    width: w, height: 260, yLabel: "mm since sowing", unit: "mm", band: bandPts, bandLabel: "1991–2020 range", lines,
    vline: asOf < season.harvest && asOf >= season.plant ? { day: asOf, label: "latest data" } : undefined,
  }));
  b.append(tableView(["Date", "This season (mm)", "Water need (mm)", "Normal median (mm)", "Normal 10–90% (mm)"],
    bandPts.filter((_, i) => i % 7 === 0 || i === k).map((bp, i2) => {
      const i = bp.day - season.plant;
      void i2;
      return [fromDay(bp.day), r1(cumR[i]), wb ? r1(wb.cumEtc[i] ?? null) : null, r1(bp.mid), `${r1(bp.lo)}–${r1(bp.hi)}`];
    }), "Show data table (weekly)"));
  if (!wb) b.append(note(`Crop water need is not computed for this crop: ${p?.kc_range ?? "no FAO-56 parameters"}.`));
  else b.append(note("Water need is ETc = Kc × ET₀ for a healthy crop without water stress (FAO-56). Shortfall uses effective rainfall (USDA-SCS method as in FAO CROPWAT), summed by month. Not included: paddy flooding, land preparation, field losses."));
  b.append(src("ERA5 reanalysis via Open-Meteo (rainfall, FAO-56 reference evapotranspiration ET₀); Kc from FAO-56 Table 12."));
  return { gap: wb ? wb.totals.gap : null, percentile };
}

// =====================================================================
function bandOnDates(bands: (Band | null)[], from: Day, to: Day) {
  const out = [];
  for (let d = from; d <= to; d++) {
    const bd = bands[dayOfYear(d)];
    if (bd) out.push({ day: d, lo: bd.p10, mid: bd.p50, hi: bd.p90 });
  }
  return out;
}
function seriesOn(obs: Daily, v: "tmax" | "tmin" | "rh" | "et0" | "sm", from: Day, to: Day, scale = 1) {
  const ix = indexOf(obs);
  const out = [];
  for (let d = from; d <= to; d++) {
    const i = ix.get(d);
    const y = i === undefined ? null : obs[v][i];
    out.push({ day: d, y: y == null ? null : y * scale });
  }
  return out;
}

function renderTemp(b: HTMLElement, c: RenderCtx, obs: Daily, range: [Day, Day], p: CropParams | null,
  season: Season | null, cmp: { season: Season; data: Daily } | null, cropLabel: string) {
  const T = theme();
  const bands = doyBands(c.clim, "tmax");
  const pts = seriesOn(obs, "tmax", range[0], range[1]);
  const valid = finite(pts.map((x) => x.y));
  const thr = p?.heat_c ?? null;
  if (valid.length) {
    const hot = thr != null ? valid.filter((v) => v > thr).length : null;
    let context = "";
    if (thr != null && season && c.cal) {
      const n = range[1] - range[0] + 1;
      const counts = hotDayCounts(c.clim, (y) => seasonForYear(c.cal!, y), n, thr);
      if (counts.length >= 10) context = ` The 1991–2020 median for the same days is ${Math.round(median(counts))}.`;
    }
    b.append(el("p", { class: "lead" },
      `Average daily maximum ${fmt.c(valid.reduce((a, x) => a + x, 0) / valid.length)} from ${fmtDay(range[0])} to ${fmtDay(range[1])}.` +
      (hot != null ? ` ${hot} day${hot === 1 ? "" : "s"} above ${thr} °C, the level above which ${cropLabel.toLowerCase()} yields are reported to fall.` + context : "")));
  }
  const lines = [{ label: "Daily maximum", color: T.this, points: pts }];
  if (cmp && season) {
    const ix = indexOf(cmp.data);
    lines.push({ label: `Season ${cmp.season.year}`, color: T.cmp, points: pts.map((pt) => {
      const i = ix.get(cmp.season.plant + (pt.day - season.plant));
      return { day: pt.day, y: i === undefined ? null : cmp.data.tmax[i] };
    }) });
  }
  b.append(legend([
    { label: "Daily maximum temperature", color: T.this, kind: "line" },
    ...(cmp ? [{ label: `Season ${cmp.season.year}`, color: T.cmp, kind: "line" as const }] : []),
    { label: "Normal range 1991–2020 (10th–90th percentile)", color: T.band, kind: "band" },
  ]));
  chart(b, (w) => timeChart({
    width: w, yLabel: "°C", unit: "°C", band: bandOnDates(bands, range[0], range[1]), lines,
    hline: thr != null ? { y: thr, label: `${thr} °C heat threshold` } : undefined,
  }));
  b.append(tableView(["Date", "Tmax (°C)", "Tmin (°C)"], seriesOn(obs, "tmax", range[0], range[1]).map((pt, i) => {
    const tmin = seriesOn(obs, "tmin", range[0], range[1])[i]?.y ?? null;
    return [fromDay(pt.day), r1(pt.y), r1(tmin)];
  })));
  if (thr != null && p?.heat_ref) b.append(note(`Heat threshold: ${c.params.references[p.heat_ref]}`));
  b.append(src("ERA5 2 m daily maximum and minimum temperature via Open-Meteo. Normal range from a ±7-day window around each date."));
}

// =====================================================================
function renderOther(b: HTMLElement, c: RenderCtx, obs: Daily, range: [Day, Day], asOf: Day): number | null {
  const T = theme();
  const g = el("div", { class: "grid3" });
  b.append(legend([
    { label: "Observed (daily)", color: T.this, kind: "line" },
    { label: "Normal range 1991–2020", color: T.band, kind: "band" },
  ]));
  b.append(g);
  const panels: { v: "rh" | "et0" | "sm"; title: string; unit: string; scale: number }[] = [
    { v: "rh", title: "Relative humidity (daily mean)", unit: "%", scale: 1 },
    { v: "et0", title: "Reference evapotranspiration ET₀", unit: "mm/day", scale: 1 },
    { v: "sm", title: "Soil moisture 0–100 cm", unit: "%", scale: 100 },
  ];
  let smPct: number | null = null;
  for (const pn of panels) {
    const cell = el("div", {}, el("h3", {}, pn.title));
    g.append(cell);
    const pts = seriesOn(obs, pn.v, range[0], range[1], pn.scale);
    if (!finite(pts.map((x) => x.y)).length) {
      cell.append(note("Not available from ERA5 at this point."));
      continue;
    }
    const bands = doyBands(c.clim, pn.v).map((bd) => bd && ({ p10: bd.p10 * pn.scale, p50: bd.p50 * pn.scale, p90: bd.p90 * pn.scale }));
    chart(cell, (w) => timeChart({ width: w, height: 180, yLabel: pn.unit, unit: pn.unit, band: bandOnDates(bands, range[0], range[1]), lines: [{ label: pn.title, color: T.this, points: pts }] }));
    if (pn.v === "sm") {
      const ix = indexOf(obs);
      const i = ix.get(Math.min(asOf, range[1]));
      const v = i === undefined ? null : obs.sm[i];
      if (v != null) {
        smPct = doyPercentile(c.clim, "sm", Math.min(asOf, range[1]), v);
        cell.append(note(`On ${fmtDay(Math.min(asOf, range[1]))}: ${(v * 100).toFixed(0)}% by volume, ${fmt.ord(smPct)} percentile for the time of year.`));
      }
    }
  }
  b.append(src("ERA5 via Open-Meteo. Soil moisture is modelled volumetric water content (m³/m³, shown as %), not a field measurement."));
  return smPct;
}

// =====================================================================
function renderForecast(b: HTMLElement, c: RenderCtx, days: EnsembleDay[], p: CropParams | null) {
  const T = theme();
  const rows = days.map((d) => ({
    day: d.day,
    p10: quantile(d.members.precip, 0.1), p50: quantile(d.members.precip, 0.5), p90: quantile(d.members.precip, 0.9),
    t10: quantile(d.members.tmax, 0.1), t50: quantile(d.members.tmax, 0.5), t90: quantile(d.members.tmax, 0.9),
  }));
  const total = rows.reduce((a, r) => a + r.p50, 0);
  b.append(el("p", { class: "lead" },
    `Median forecast rain over ${rows.length} days: ${fmt.mm(total)}. Maximum temperatures ${fmt.c(Math.min(...rows.map((r) => r.t50)))} to ${fmt.c(Math.max(...rows.map((r) => r.t50)))}.`));
  const g = el("div", { class: "grid2" });
  b.append(g);
  const c1 = el("div", {}, el("h3", {}, "Daily rain"), legend([{ label: "Ensemble median", color: T.this, kind: "dot" }, { label: "10th–90th percentile of members", color: T.ink2, kind: "line" }]));
  const c2 = el("div", {}, el("h3", {}, "Daily maximum temperature"), legend([
    { label: "Ensemble median", color: T.this, kind: "line" }, { label: "Normal (1991–2020 median)", color: T.band, kind: "line" },
    { label: "Ensemble 10th–90th percentile", color: T.band, kind: "band" }]));
  g.append(c1, c2);
  chart(c1, (w) => forecastRain(w, rows));
  const clim = doyBands(c.clim, "tmax");
  chart(c2, (w) => timeChart({
    width: w, height: 200, yLabel: "°C", unit: "°C",
    band: rows.map((r) => ({ day: r.day, lo: r.t10, mid: r.t50, hi: r.t90 })), bandLabel: "Ensemble 10–90%",
    lines: [
      { label: "Ensemble median", color: T.this, points: rows.map((r) => ({ day: r.day, y: r.t50 })) },
      { label: "Normal median", color: T.band, points: rows.map((r) => ({ day: r.day, y: clim[dayOfYear(r.day)]?.p50 ?? null })) },
    ],
    hline: p?.heat_c != null ? { y: p.heat_c, label: `${p.heat_c} °C` } : undefined,
  }));
  b.append(tableView(["Date", "Rain median (mm)", "Rain 10–90% (mm)", "Tmax median (°C)", "Tmax 10–90% (°C)"],
    rows.map((r) => [fromDay(r.day), r1(r.p50), `${r1(r.p10)}–${r1(r.p90)}`, r1(r.t50), `${r1(r.t10)}–${r1(r.t90)}`])));
  b.append(src(`ECMWF IFS 0.25° ensemble (${days[0]?.members.precip.length ?? 0} members) via Open-Meteo, issued daily.`));
}

function renderSeasonal(b: HTMLElement, months: SeasonalMonth[], season: Season | null, next: Season | null, inSeason: boolean,
  plan: StagePlan | null, nextPlan: StagePlan | null) {
  const items = months.map((m) => {
    const mm = Number(m.month.slice(5, 7));
    return {
      label: `${monthName(mm)} ${m.month.slice(2, 4)}`,
      value: m.precipPct,
      note: `${m.precipMm != null ? Math.round(m.precipMm) + " mm forecast" : ""}${m.tAnom != null ? `; temperature ${m.tAnom > 0 ? "+" : ""}${m.tAnom.toFixed(1)} °C vs model normal` : ""}`,
    };
  });
  b.append(el("p", { class: "lead" }, "Rainfall compared with the forecast model's own normal for each month. Brown is drier, blue is wetter."));
  chart(b, (w) => anomalyBars({ width: w, items, unit: "%", yLabel: "% vs model normal" }));
  const target = inSeason ? season : next;
  const tp = inSeason ? plan : nextPlan;
  if (target && tp) {
    const m0 = target.plant + tp.bounds[1];
    const m1 = target.plant + tp.bounds[2] - 1;
    b.append(note(`Mid-season stage of the ${inSeason ? "current" : "next"} season: ${fmtDay(m0)} – ${fmtDay(m1)}.`));
  }
  b.append(tableView(["Month", "Rain (mm)", "Rain vs model normal", "Temperature vs model normal"], months.map((m) => [
    m.month, m.precipMm != null ? Math.round(m.precipMm) : null,
    m.precipPct != null ? `${m.precipPct > 0 ? "+" : ""}${Math.round(m.precipPct)}%` : null,
    m.tAnom != null ? `${m.tAnom > 0 ? "+" : ""}${m.tAnom.toFixed(1)} °C` : null,
  ])));
  b.append(note("Seasonal forecasts show tendencies over a wide area, are not bias-corrected, and are often wrong at a single place."));
  b.append(src("ECMWF SEAS5 (51 members, monthly ensemble mean and anomaly vs SEAS5 hindcast climatology) via Open-Meteo Seasonal API."));
}

// =====================================================================
function renderAfter(b: HTMLElement, c: RenderCtx, obs: Daily, D: Day) {
  const T = theme();
  const last = lastEra5Day();
  const end16 = Math.min(D + 16, last);
  if (end16 <= D) { b.append(note("No observations after this date yet.")); return; }
  const ix = indexOf(obs);
  let rain = 0;
  for (let d = D + 1; d <= end16; d++) rain += obs.precip[ix.get(d) ?? -1] ?? 0;
  // Normal for the same 16 calendar days
  const sums: number[] = [];
  const cix = indexOf(c.clim);
  for (let y = 1991; y <= 2020; y++) {
    const start = toDay(`${y}-${fromDay(D + 1).slice(5)}`.replace("-02-29", "-02-28"));
    let s = 0; let ok = true;
    for (let k = 0; k < end16 - D; k++) { const v = c.clim.precip[cix.get(start + k) ?? -1]; if (v == null) { ok = false; break; } s += v; }
    if (ok) sums.push(s);
  }
  b.append(el("p", { class: "lead" },
    `Next ${end16 - D} days after ${fmtDay(D)}: ${fmt.mm(rain)} of rain` +
    (sums.length ? ` (1991–2020 median for those days ${fmt.mm(median(sums))}, ${fmt.ord(percentileRank(sums, rain))} percentile).` : ".")));
  chart(b, (w) => timeChart({
    width: w, height: 200, yLabel: "°C", unit: "°C", band: bandOnDates(doyBands(c.clim, "tmax"), D + 1, end16),
    lines: [{ label: "Daily maximum", color: T.this, points: seriesOn(obs, "tmax", D + 1, end16) }],
  }));
  const months = monthlyVsNormal(obs, c.clim, D + 1, Math.min(D + 214, last));
  if (months.length) {
    b.append(el("h3", {}, "Monthly rain in the following months vs 1991–2020 mean"));
    chart(b, (w) => anomalyBars({ width: w, unit: "%", yLabel: "% vs 1991–2020", items: months.map((m) => ({ label: `${monthName(m.m)} ${String(m.y).slice(2)}`, value: m.pct, note: `${Math.round(m.rain)} mm (normal ${Math.round(m.normal)} mm)` })) }));
    b.append(tableView(["Month", "Rain (mm)", "1991–2020 mean (mm)", "Departure"], months.map((m) => [`${m.y}-${String(m.m).padStart(2, "0")}`, Math.round(m.rain), Math.round(m.normal), m.pct != null ? `${Math.round(m.pct)}%` : null])));
  }
  b.append(src("ERA5 via Open-Meteo."));
}

// =====================================================================
function renderEnso(b: HTMLElement, c: RenderCtx, D: Day, current: boolean, season: Season | null, onComposite: (x: Composite | null) => void) {
  const e = c.enso;
  if (!e) { b.append(note("ENSO data file is missing (run the ENSO workflow).", "note error")); return; }
  const T = theme();
  const [y0, m0] = e.start.split("-").map(Number);
  const series = e.values.map((v, i) => ({ date: new Date(Date.UTC(y0, m0 - 1 + i, 15)), v })).filter((x): x is { date: Date; v: number } => x.v != null);
  const eps = e.episodes.map((ep) => ({ type: ep.type, start: new Date(ep.start + "-01"), end: new Date(ep.end + "-28") }));

  const { y, m } = ymd(D);
  const val = current ? e.latest.value : indexValue(e, y, m);
  const when = current ? e.latest.month : `${y}-${String(m).padStart(2, "0")}`;
  const months = episodeMonths(e);
  const phaseThen = months.get(`${y}-${m}`);
  const lead = current
    ? `Latest ${e.index} (${when}, 3-month mean centred on this month): ${val != null ? (val > 0 ? "+" : "") + val.toFixed(2) + " °C" : "n/a"}. ` +
      (e.run_in_progress ? `${e.run_in_progress.type === "El Nino" ? "El Niño" : "La Niña"}-level values for ${e.run_in_progress.seasons_so_far} consecutive season${e.run_in_progress.seasons_so_far > 1 ? "s" : ""}${e.run_in_progress.seasons_so_far >= 5 ? " (an episode by NOAA's definition)." : " (five are needed for an episode)."}` : "Neutral range (between −0.5 and +0.5 °C).")
    : `${e.index} in ${when}: ${val != null ? (val > 0 ? "+" : "") + val.toFixed(2) + " °C" : "n/a"}` + (phaseThen ? `, during a ${phaseThen === "El Nino" ? "El Niño" : "La Niña"} episode.` : ", not during an ENSO episode.");
  b.append(el("p", { class: "lead" }, lead));
  b.append(legend([{ label: `${e.index} (°C)`, color: T.ink2, kind: "line" }, { label: "El Niño episode", color: T.nino, kind: "band" }, { label: "La Niña episode", color: T.nina, kind: "band" }]));
  chart(b, (w) => ensoTimeline(w, series, eps, current ? undefined : toDate(D)));
  b.append(src(`NOAA CPC ${e.index === "RONI" ? "Relative Oceanic Niño Index" : "Oceanic Niño Index"}, ${e.index_source}. Updated ${e.generated_utc}.`));

  if (current && e.seas5_nino34?.months?.length) {
    const s5 = e.seas5_nino34;
    b.append(el("h3", {}, "Model outlook for the Niño-3.4 region"));
    b.append(el("p", {}, s5.months.map((mo, i) => `${monthName(Number(mo.slice(5)))}: ${s5.anomaly_c[i] != null ? (s5.anomaly_c[i]! > 0 ? "+" : "") + s5.anomaly_c[i]!.toFixed(1) + " °C" : "n/a"}`).join(" · ")));
    b.append(note(s5.description));
    const links = el("p", { class: "note" }, "Official outlooks: ",
      el("a", { href: "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml" }, "NOAA CPC ENSO diagnostic discussion"),
      " · ",
      el("a", { href: "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/" }, "IRI ENSO forecast"));
    b.append(links);
  }

  // Local composites
  b.append(el("h3", {}, "What happened here in past El Niño and La Niña seasons"));
  const cal: Calendar = c.cal ?? (() => {
    const start = toDay(`2001-${String(m).padStart(2, "0")}-01`);
    return { plantDoy: dayOfYear(start), maturityDoy: ((dayOfYear(start) + 182 - 1) % 365) + 1 };
  })();
  const what = c.cal ? `the ${c.params.ggcmi_labels[c.cropKey!.slice(0, 3)].toLowerCase()} season (${doyLabel(cal.plantDoy)} – ${doyLabel(cal.maturityDoy)})`
    : `the six months from ${monthName(m)} (no crop calendar here)`;
  const holder = el("div");
  const btn = el("button", { class: "link", type: "button" }, "Load El Niño history for this place");
  holder.append(el("p", {}, `Compares rainfall and temperature in ${what} for every year since 1950, grouped by NOAA ENSO episodes. `), btn,
    note("This downloads about 70 years of daily ERA5 data (roughly 1 MB, then cached)."));
  b.append(holder);
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Loading…";
    try {
      c.setStatus(S.status.enso);
      const lat = c.state.lat!;
      const lon = c.state.lon!;
      const [a1, a2] = await Promise.all([
        era5Daily(lat, lon, toDay("1950-01-01"), toDay("1990-12-31"), ["precip", "tmax", "tmin"], (msg) => c.setStatus(msg)),
        era5Daily(lat, lon, toDay("2021-01-01"), lastEra5Day(), ["precip", "tmax", "tmin"], (msg) => c.setStatus(msg)),
      ]);
      if (!c.alive()) return;
      const all = mergeDaily([a1.data, c.clim, a2.data]);
      const seasonFor = (yy: number) => seasonForYear(cal, yy);
      let lastY = ymd(lastEra5Day()).y;
      while (seasonFor(lastY).harvest > lastEra5Day()) lastY--;
      const totals = seasonTotals(all, seasonFor, 1950, lastY);
      const comp = composite(totals, seasonFor, e);
      holder.replaceChildren();
      if (!comp) { holder.append(note("Not enough complete seasons to compare.")); return; }
      renderComposite(holder, comp, what, season ? [season.year, ...(c.state.cmp ? [c.state.cmp] : [])] : []);
      c.setStatus(S.status.done);
      onComposite(comp);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Retry";
      c.setStatus(`El Niño history failed: ${(err as Error).message}`, true);
    }
  });
  void seasonPhase;
}

function renderComposite(b: HTMLElement, comp: Composite, what: string, highlight: number[]) {
  const n = comp.byPhase["El Nino"];
  const neu = comp.byPhase["Neutral"];
  const sig = comp.pRainNinoVsNeutral < 0.05;
  const dir = n.medianRainPct < neu.medianRainPct ? "drier" : "wetter";
  const pTxt = `permutation test p = ${comp.pRainNinoVsNeutral < 0.001 ? "<0.001" : comp.pRainNinoVsNeutral.toFixed(3)}`;
  b.append(el("p", { class: "lead" }, n.n === 0
    ? "No El Niño season in the record for this crop season."
    : sig
      ? `El Niño seasons here were ${dir} than neutral seasons: median ${fmt.pct(n.medianRainPct)} vs ${fmt.pct(neu.medianRainPct)} against the 1991–2020 normal. ${n.drierCount} of ${n.n} El Niño seasons were below normal (${pTxt}).`
      : `No clear El Niño effect on rainfall in ${what}: median ${fmt.pct(n.medianRainPct)} in El Niño seasons vs ${fmt.pct(neu.medianRainPct)} in neutral seasons; ${n.drierCount} of ${n.n} El Niño seasons were below normal (${pTxt}).`));
  const T = theme();
  const g = el("div", { class: "grid2" });
  const c1 = el("div", {}, el("h3", {}, "Season rainfall vs 1991–2020 normal"));
  const c2 = el("div", {}, el("h3", {}, "Season temperature vs long-term trend"));
  g.append(c1, c2);
  b.append(legend([{ label: "El Niño season", color: T.nino, kind: "dot" }, { label: "Neutral", color: T.neutral, kind: "dot" }, { label: "La Niña season", color: T.nina, kind: "dot" }, { label: "Median (bar); outlined = selected season", color: T.ink, kind: "line" }]));
  b.append(g);
  chart(c1, (w) => compositeDots(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.rainPct })), "%", "% vs normal", highlight));
  chart(c2, (w) => compositeDots(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.tempAnom })), " °C", "°C", highlight));
  const tSig = comp.pTempNinoVsNeutral < 0.05;
  b.append(note(`Temperature: El Niño median ${fmt.dc(n.medianTempAnom)} vs neutral ${fmt.dc(neu.medianTempAnom)} (${tSig ? "" : "not "}significant, p = ${comp.pTempNinoVsNeutral.toFixed(3)}). Temperatures are shown after removing the linear warming trend.`));
  b.append(tableView(["Season", "Phase", "Rain (mm)", "Rain vs normal", "Temp vs trend (°C)"],
    [...comp.points].reverse().map((p) => [String(p.year), p.phase === "El Nino" ? "El Niño" : p.phase === "La Nina" ? "La Niña" : "Neutral", Math.round(p.rain), `${Math.round(p.rainPct)}%`, r1(p.tempAnom)])));
  b.append(note(`Seasons ${comp.firstYear}–${comp.lastYear}. A season counts as El Niño or La Niña when more than half its days fall in a NOAA CPC episode. Normal = mean of 1991–2020 seasons (${Math.round(comp.normalRain)} mm).`));
  b.append(src("ERA5 via Open-Meteo; ENSO episodes from NOAA CPC. Past seasons show what happened, not a forecast: each El Niño is different."));
}

// =====================================================================
function renderAdvice(b: HTMLElement, items: Advice[]) {
  if (!items.length) {
    b.append(el("p", { class: "lead" }, "Nothing unusual is flagged for this crop from the current data. Continue normal practice."));
  } else {
    const ul = el("ul", { class: "advice" });
    for (const a of items) {
      ul.append(el("li", {},
        el("div", { class: "t" }, a.title),
        el("div", {}, a.action),
        el("div", { class: "why" }, `Why: ${a.trigger}`),
        el("div", { class: "srcline" }, `Source: ${a.source}`)));
    }
    b.append(ul);
  }
  b.append(note("Checks run: season rainfall vs normal, soil moisture, heat and heavy rain in the 15-day forecast, SEAS5 outlook for the sensitive stage, and El Niño history (after it is loaded). Confirm any decision with your local extension service."));
}
