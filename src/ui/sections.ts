import { Day, dayOfYear, fmtDay, fromDay, monthName, toDate, toDay, todayDay, ymd } from "../lib/dates";
import { CropParamFile, LocalCrops } from "../api/static";
import { EnsembleDay, GridInfo, SeasonalMonth, era5Daily, ensembleForecast, lastEra5Day, mergeDaily, seasonalMonthly } from "../api/openmeteo";
import {
  Band, Daily, cumulative, cumulativeRainBand, doyBands, doyPercentile, hotDayCounts, indexOf,
  monthlyVsNormal, seasonTotals, waterBalance,
} from "../calc/climate";
import { Calendar, CropParams, STAGE_NAMES, Season, seasonForYear, seasonStatus, stageIndex, stagePlan, StagePlan } from "../calc/season";
import { Composite, EnsoData, composite, episodeMonths, indexValue } from "../calc/enso";
import { finite, median, percentileRank, quantile } from "../calc/stats";
import { Advice, buildAdvice } from "../calc/advice";
import { S } from "../strings";
import { cropName } from "../lib/cropnames";
import { Block, block, chart, el, fmt, more, note, resetCharts } from "./dom";
import { icon } from "./icons";
import { compositeDots, ensoTimeline, forecastRain, legend, r1, tableView, theme, timeChart } from "./charts";
import { CalRow, Tone, cropCalendar, forecastStrip, meter, outlookTiles, pictogram, ring, supplyNeed, tile } from "./visuals";
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

const pctTone = (p: number | null): Tone =>
  p == null ? "neutral" : p < 10 ? "severe" : p < 20 ? "concern" : p < 33 ? "watch" : p > 90 ? "watch" : "good";

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
  const sys = c.cropKey?.endsWith("_ir") ? "irrigated" : "rainfed";
  const p: CropParams | null = code ? c.params.params[c.params.ggcmi_to_param[code]] ?? null : null;

  // ---------------------------------------------------------------- place header
  const head = el("section", { class: "place" },
    el("div", { class: "place-ico" }, icon("pin", 22)),
    el("div", {},
      el("h2", { id: "place-name" }, c.state.name ?? `${c.state.lat!.toFixed(3)}, ${c.state.lon!.toFixed(3)}`),
      el("div", { class: "chips" },
        el("span", { class: "chip" }, `${Math.round(c.grid.elevation)} m`),
        el("span", { class: "chip" }, current ? `Data to ${fmtDay(last)}` : `As of ${fmtDay(D)}`),
        code ? el("span", { class: "chip strong" }, `${cropLabel} · ${sys}`) : null)));
  c.root.append(head);
  if (!current) {
    c.root.append(el("div", { class: "banner" }, icon("calendar", 18),
      el("span", {}, `Looking back at ${fmtDay(D)}. Forecasts are replaced by what actually happened next.`)));
  }

  // ---------------------------------------------------------------- overview + nav
  const tiles = el("div", { class: "tiles" });
  c.root.append(tiles);
  const slots: Record<string, HTMLElement> = {};
  for (const k of ["season", "rain", "heat", "soil", "enso"]) {
    slots[k] = el("div", { class: "tile-slot" });
    tiles.append(slots[k]);
  }
  const put = (k: string, t: HTMLElement | null) => { if (t) slots[k].replaceChildren(t); else slots[k].remove(); };

  const nav = el("nav", { class: "secnav", "aria-label": "Sections" });
  c.root.append(nav);
  const addNav = (id: string, label: string) => nav.append(el("a", { href: `#${id}` }, label));

  // ---------------------------------------------------------------- crops
  addNav("crops", "Crops");
  const crops = block(c.root, S.h.here, { id: "crops", icon: "sprout" });
  renderCrops(crops, c, asOf);

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
  if (c.cal && season) renderStrip(crops, c, season, nextSeason!, inSeason, dayOfSeason, plan, asOf, cropLabel);

  // Season tile
  if (season && c.cal) {
    if (inSeason) {
      const stage = plan ? STAGE_NAMES[stageIndex(plan, dayOfSeason)] : "In season";
      put("season", tile({ ico: "sprout", title: cropLabel, visual: ring(dayOfSeason / season.length, `${Math.round((100 * dayOfSeason) / season.length)}%`, theme().sprout), value: stage, caption: `Day ${dayOfSeason} of ${season.length}`, target: "crops" }));
    } else {
      const days = nextSeason!.plant - asOf;
      put("season", tile({ ico: "calendar", title: cropLabel, value: `${days} days`, caption: `until sowing (~${fmtDay(nextSeason!.plant)})`, target: "crops" }));
    }
  } else put("season", null);

  // ---------------------------------------------------------------- fetch observations
  c.setStatus(S.status.season);
  const from: Day = season ? Math.min(season.plant, asOf - 30) : asOf - 150;
  const to: Day = current ? last : Math.min(last, Math.max(season?.harvest ?? D, D + 214));
  const obs = (await era5Daily(c.state.lat!, c.state.lon!, from, to, ["precip", "tmax", "tmin", "et0", "rh", "sm"], (m) => c.setStatus(m))).data;
  if (!c.alive()) return;
  let cmp: { season: Season; data: Daily } | null = null;
  if (c.cal && c.state.cmp) {
    const cs = seasonForYear(c.cal, c.state.cmp);
    const d = (await era5Daily(c.state.lat!, c.state.lon!, cs.plant, cs.harvest, ["precip", "tmax"])).data;
    cmp = { season: cs, data: d };
    if (!c.alive()) return;
  }

  // ---------------------------------------------------------------- water
  let gapMm: number | null = null;
  let rainPct: number | null = null;
  if (c.cal && season) {
    addNav("water", "Water");
    const b = block(c.root, S.h.water, { id: "water", icon: "drop" });
    const r = renderWater(b, c, season, obs, asOf, p, cmp, cropLabel);
    gapMm = r.gap; rainPct = r.percentile;
    put("rain", tile({ ico: "drop", title: inSeason ? "Rain since sowing" : "Last season's rain", visual: r.percentile != null ? meter(r.percentile, "Dry", "Wet", 150) : undefined, value: r.pctOfNormal != null ? `${Math.round(r.pctOfNormal)}% of normal` : undefined, tone: pctTone(r.percentile), target: "water" }));
  } else put("rain", null);

  // ---------------------------------------------------------------- temperature
  addNav("temp", "Heat");
  const range: [Day, Day] = season ? [season.plant, Math.min(season.harvest, asOf)] : [asOf - 120, asOf];
  const tb = block(c.root, S.h.temp, { id: "temp", icon: "thermo" });
  const heat = renderTemp(tb, c, obs, range, p, season, cmp, cropLabel);
  if (heat.hot != null) {
    const tone: Tone = heat.normal == null ? "neutral" : heat.hot >= 5 && heat.hot > heat.normal * 1.5 ? "concern" : heat.hot > heat.normal ? "watch" : "good";
    put("heat", tile({ ico: "thermo", title: `Days above ${p!.heat_c} °C`, value: String(heat.hot), caption: heat.normal != null ? `normal: ${Math.round(heat.normal)}` : undefined, tone, target: "temp" }));
  } else {
    put("heat", tile({ ico: "thermo", title: "Average max", value: heat.avg != null ? fmt.c(heat.avg) : "–", caption: "this season", target: "temp" }));
  }

  // ---------------------------------------------------------------- soil & air
  addNav("soil", "Soil & air");
  const ob = block(c.root, S.h.other, { id: "soil", icon: "soil" });
  const smPct = renderOther(ob, c, obs, range, asOf);
  put("soil", smPct != null ? tile({ ico: "soil", title: "Soil moisture", visual: meter(smPct, "Dry", "Wet", 150), value: `${fmt.ord(smPct)} percentile`, tone: pctTone(smPct), target: "soil" }) : null);

  // ---------------------------------------------------------------- forecast / what happened next
  let fc: EnsembleDay[] | null = null;
  let seas: SeasonalMonth[] | null = null;
  if (current) {
    c.setStatus(S.status.forecast);
    addNav("fc", "15 days");
    const fb = block(c.root, S.h.fc, { id: "fc", icon: "rain" });
    addNav("seas", "7 months");
    const sb = block(c.root, S.h.seas, { id: "seas", icon: "calendar" });
    const [f, s] = await Promise.allSettled([ensembleForecast(c.state.lat!, c.state.lon!), seasonalMonthly(c.state.lat!, c.state.lon!)]);
    if (!c.alive()) return;
    if (f.status === "fulfilled") { fc = f.value.days; renderForecast(fb, c, fc, p); }
    else fb.body.append(note(`Forecast unavailable: ${(f.reason as Error).message}`, "note error"));
    if (s.status === "fulfilled") { seas = s.value; renderSeasonal(sb, seas, inSeason ? season : nextSeason, inSeason ? plan : seasonPlanFor(nextSeason, p)); }
    else sb.body.append(note(`Seasonal forecast unavailable: ${(s.reason as Error).message}`, "note error"));
  } else {
    addNav("after", "Afterwards");
    renderAfter(block(c.root, S.h.after, { id: "after", icon: "chart" }), c, obs, D);
  }

  // ---------------------------------------------------------------- El Nino
  addNav("enso", "El Niño");
  const eb = block(c.root, S.h.enso, { id: "enso", icon: "wave" });
  put("enso", ensoTile(c.enso, D, current));

  // ---------------------------------------------------------------- advice
  let adv: Block | null = null;
  if (current) {
    addNav("advice", "What to do");
    adv = block(c.root, S.h.advice, { id: "advice", icon: "check" });
    adv.info(
      "Checks: rain since sowing, soil moisture, heat and heavy rain in the 15-day forecast, the 7-month outlook for the coming or current season, and El Niño.",
      "Each card appears only when the data trigger it. Tap (i) on a card to see why and the source. Always confirm with your local extension service.");
  }
  const advice = (comp: Composite | null) => {
    if (!adv) return;
    adv.body.replaceChildren();
    if (!c.cal || !season) { adv.body.append(note("Needs a crop calendar, which is not available here.")); return; }
    const target = inSeason ? season : nextSeason!;
    const items = buildAdvice({
      cropLabel, season: target, inSeason, today,
      plan: p?.stages ? stagePlan(p.stages, target.length) : null,
      heatC: p?.heat_c ?? null, heatRef: p?.heat_ref ?? null,
      rainPercentile: inSeason ? rainPct : null, gapMm: inSeason ? gapMm : null,
      smPercentile: smPct, forecast: fc, seasonal: seas, composite: comp,
      ensoNow: c.enso?.run_in_progress ?? null, references: c.params.references,
    });
    renderAdvice(adv.body, items);
  };
  renderEnso(eb, c, D, current, season, (comp) => advice(comp));
  advice(null);

  // ---------------------------------------------------------------- limits
  c.root.append(more("Limits of this page", el("ul", { class: "limits" }, ...S.limits.map((t) => el("li", {}, t)))));
}

function seasonPlanFor(s: Season | null, p: CropParams | null): StagePlan | null {
  return s && p?.stages ? stagePlan(p.stages, s.length) : null;
}

function doyLabel(doy: number): string {
  const d = toDate(toDay("2001-01-01") + doy - 1);
  return `${d.getUTCDate()} ${monthName(d.getUTCMonth() + 1)}`;
}

// =====================================================================
function renderCrops(b: Block, c: RenderCtx, asOf: Day) {
  b.info(el("p", { class: "src" }, "CROPGRIDS v1.08, harvested area circa 2020 (Tang et al. 2024), aggregated to 0.25° (~28 km). Sowing and maturity: GGCMI Phase 3 crop calendar (Jägermeyr et al. 2021), 0.5°."));
  if (!c.cropsLoaded) {
    b.body.append(note("Crop map not available yet.", "note error"));
    return;
  }
  const L = c.local;
  if (L.totalHa < MIN_CROPLAND_HA) {
    b.body.append(el("div", { class: "empty" }, icon("sprout", 28), el("p", {}, "No cropland recorded here. Weather and climate below still apply.")));
    return;
  }
  const pctCell = L.totalHa / L.cellKm2;
  b.info(`About ${Math.round(L.totalHa).toLocaleString("en")} ha of crops are harvested in this cell each year, equal to ${pctCell < 1 ? "<1" : Math.round(pctCell)}% of its area. Harvested area counts land cropped twice a year twice. The grey bar beside each crop is its share of that area.`);

  const rows: CalRow[] = [];
  const noCal: string[] = [];
  for (const cr of L.crops) {
    const keys = cr.ggcmi.flatMap((g) => ["rf", "ir"].map((s) => `${g}_${s}`)).filter((k) => L.calendars[k]);
    if (!keys.length) { noCal.push(`${cropName(cr.name)} ${Math.round(cr.share * 100)}%`); continue; }
    // one row per GGCMI crop code (e.g. spring and winter wheat separately)
    const codes = [...new Set(keys.map((k) => k.slice(0, 3)))];
    codes.forEach((g, gi) => {
      const ks = keys.filter((k) => k.startsWith(g));
      rows.push({
        label: codes.length > 1 ? c.params.ggcmi_labels[g] : cropName(cr.name),
        share: gi === 0 ? cr.share : null,
        windows: ks.map((k) => ({ plant: L.calendars[k][0], mature: L.calendars[k][1], irrigated: k.endsWith("_ir") })),
        selected: c.cropKey?.startsWith(g) ?? false,
      });
    });
  }
  const T = theme();
  b.body.append(legend([{ label: "Rainfed season", color: T.sprout, kind: "band" }, { label: "Irrigated season", color: T.this, kind: "band" }, { label: "Share of crop area", color: T.ink2, kind: "band" }]));
  chart(b.body, (w) => cropCalendar(rows, dayOfYear(asOf), w));
  if (noCal.length) b.body.append(el("p", { class: "also" }, el("strong", {}, "Also grown: "), noCal.join(" · ")));
}

// =====================================================================
function renderStrip(b: Block, c: RenderCtx, season: Season, next: Season, inSeason: boolean, dos: number,
  plan: StagePlan | null, asOf: Day, cropLabel: string) {
  const t = theme();
  const cs = getComputedStyle(document.documentElement);
  const stageCol = cs.getPropertyValue("--stage").trim();
  const midCol = cs.getPropertyValue("--stage-mid").trim();
  b.body.append(el("h3", { class: "sub" }, inSeason ? `${cropLabel}: this season` : `${cropLabel}: last season`,
    !inSeason ? el("span", { class: "muted" }, ` · next sowing ~${fmtDay(next.plant)}`) : null));
  const H = 64;
  const draw = (W: number) => {
    const x = (d: Day) => ((d - season.plant) / season.length) * (W - 20) + 10;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", String(W));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Crop stages across the season");
    const add = (tag: string, a: Record<string, string | number>, text?: string) => {
      const e = document.createElementNS(svg.namespaceURI, tag);
      Object.entries(a).forEach(([k, v]) => e.setAttribute(k, String(v)));
      if (text) e.textContent = text;
      svg.append(e);
    };
    if (plan) {
      let prev = 0;
      plan.bounds.forEach((bd, i) => {
        const x0 = x(season.plant + prev);
        const x1 = x(season.plant + bd);
        add("rect", { x: x0 + 1, y: 8, width: Math.max(0, x1 - x0 - 2), height: 26, rx: 5, fill: i === 2 ? midCol : stageCol });
        const name = i === 2 ? "Flowering / grain fill" : STAGE_NAMES[i];
        if (x1 - x0 > (i === 2 ? 130 : 70)) add("text", { x: (x0 + x1) / 2, y: 25, "text-anchor": "middle", "font-size": 12, fill: t.ink }, name);
        else if (i === 2 && x1 - x0 > 60) add("text", { x: (x0 + x1) / 2, y: 25, "text-anchor": "middle", "font-size": 12, fill: t.ink }, "Flowering");
        prev = bd;
      });
    } else {
      add("rect", { x: x(season.plant), y: 8, width: x(season.harvest) - x(season.plant), height: 26, rx: 5, fill: stageCol });
    }
    add("text", { x: 10, y: 52, "font-size": 11.5, fill: t.ink2 }, `Sow ${fmtDay(season.plant)}`);
    add("text", { x: W - 10, y: 52, "font-size": 11.5, fill: t.ink2, "text-anchor": "end" }, `Mature ${fmtDay(season.harvest)}`);
    if (inSeason) {
      const xm = x(asOf);
      add("line", { x1: xm, x2: xm, y1: 2, y2: 40, stroke: t.ink, "stroke-width": 2.5 });
      add("circle", { cx: xm, cy: 3, r: 4, fill: t.ink });
    }
    return svg;
  };
  chart(b.body, draw);
  b.info(
    `The four FAO-56 stages scaled to this place's season (GGCMI sowing and maturity dates). The highlighted mid-season stage covers flowering and grain or yield formation: water shortage then costs the most yield (FAO-33). Stage proportions: ${c.params.params[c.params.ggcmi_to_param[c.cropKey!.slice(0, 3)]]?.stage_row ?? "not available"}.`);
  void dos;
}

// =====================================================================
function renderWater(b: Block, c: RenderCtx, season: Season, obs: Daily, asOf: Day, p: CropParams | null,
  cmp: { season: Season; data: Daily } | null, cropLabel: string): { gap: number | null; percentile: number | null; pctOfNormal: number | null } {
  const L = season.length + 1;
  const { bands, curves, years } = cumulativeRainBand(c.clim, (y) => seasonForYear(c.cal!, y), L);
  const cumR = cumulative(obs, "precip", season.plant, L);
  const wb = p ? waterBalance(obs, season, p, asOf) : null;

  let k = -1;
  cumR.forEach((v, i) => { if (v != null && season.plant + i <= asOf) k = i; });
  let percentile: number | null = null;
  if (k >= 0 && curves.length >= 10) percentile = percentileRank(curves.map((cv) => cv[k]), cumR[k]!);
  const normal = k >= 0 ? bands[k]?.p50 : undefined;
  const pctOfNormal = normal && normal > 0 ? (100 * cumR[k]!) / normal : null;

  // Headline visuals: big % of normal + meter, rain vs need bars
  const kpis = el("div", { class: "kpis" });
  if (k >= 0) {
    kpis.append(el("div", { class: "kpi" },
      el("div", { class: "kpi-v" }, pctOfNormal != null ? `${Math.round(pctOfNormal)}%` : fmt.mm(cumR[k]!)),
      el("div", { class: "kpi-l" }, pctOfNormal != null ? `of normal rain · ${fmt.mm(cumR[k]!)}` : "rain since sowing"),
      percentile != null ? meter(percentile, "Dry", "Wet", 200) : null));
  }
  if (wb && wb.totals.days > 0) {
    kpis.append(el("div", { class: "kpi" },
      el("div", { class: "kpi-v" }, fmt.mm(wb.totals.gap)),
      el("div", { class: "kpi-l" }, "short of crop need"),
      supplyNeed(wb.totals.effRain, wb.totals.etc, 210)));
  }
  b.body.append(kpis);

  const T = theme();
  const bandPts = bands.map((bd: Band, i) => ({ day: season.plant + i, lo: bd.p10, mid: bd.p50, hi: bd.p90 }));
  const lines = [{ label: "This season", color: T.this, points: cumR.map((y, i) => ({ day: season.plant + i, y: season.plant + i <= asOf ? y : null })) }];
  if (wb) lines.push({ label: `${cropLabel} water need`, color: T.need, points: wb.cumEtc.map((y, i) => ({ day: season.plant + i, y })) });
  if (cmp) {
    const cc = cumulative(cmp.data, "precip", cmp.season.plant, L);
    lines.push({ label: `Season ${cmp.season.year}`, color: T.cmp, points: cc.map((y, i) => ({ day: season.plant + i, y })) });
  }
  b.body.append(legend([
    { label: "Rain this season", color: T.this, kind: "line" },
    ...(wb ? [{ label: "Crop water need", color: T.need, kind: "line" as const }] : []),
    ...(cmp ? [{ label: `Season ${cmp.season.year}`, color: T.cmp, kind: "line" as const }] : []),
    { label: "Normal range", color: T.band, kind: "band" },
  ]));
  chart(b.body, (w) => timeChart({
    width: w, height: 250, yLabel: "mm since sowing", unit: "mm", band: bandPts, bandLabel: "Normal range", lines,
    vline: asOf < season.harvest && asOf >= season.plant ? { day: asOf, label: "today" } : undefined,
  }));
  b.body.append(more("Data table", tableView(["Date", "This season (mm)", "Water need (mm)", "Normal median (mm)", "Normal 10–90% (mm)"],
    bandPts.filter((_, i) => i % 7 === 0 || i === k).map((bp) => {
      const i = bp.day - season.plant;
      return [fromDay(bp.day), r1(cumR[i]), wb ? r1(wb.cumEtc[i] ?? null) : null, r1(bp.mid), `${r1(bp.lo)}–${r1(bp.hi)}`];
    }), "Weekly values")));

  b.info(
    k >= 0 ? `Rain from ${fmtDay(season.plant)} to ${fmtDay(season.plant + k)}: ${fmt.mm(cumR[k]!)}${percentile != null ? `, the ${fmt.ord(percentile)} percentile of the same days in 1991–2020` : ""}. Normal range (10th–90th percentile, ${years.length} seasons): ${k >= 0 && bands[k] ? `${fmt.mm(bands[k].p10)} – ${fmt.mm(bands[k].p90)}` : "n/a"}.` : "",
    wb ? `Crop water need so far: ${fmt.mm(wb.totals.etc)} (FAO-56 ETc = Kc × ET₀, healthy crop without water stress). Effective rain: ${fmt.mm(wb.totals.effRain)} (USDA-SCS method, as in FAO CROPWAT). Shortfall = need not covered by effective rain, summed by month. Not included: paddy flooding, land preparation, field losses.`
      : `Crop water need is not computed for this crop: ${p?.kc_range ?? "no FAO-56 parameters"}.`,
    el("p", { class: "src" }, "ERA5 rainfall and FAO-56 reference evapotranspiration via Open-Meteo; Kc from FAO-56 Table 12."));
  return { gap: wb ? wb.totals.gap : null, percentile, pctOfNormal };
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

function renderTemp(b: Block, c: RenderCtx, obs: Daily, range: [Day, Day], p: CropParams | null,
  season: Season | null, cmp: { season: Season; data: Daily } | null, cropLabel: string): { hot: number | null; normal: number | null; avg: number | null } {
  const T = theme();
  const bands = doyBands(c.clim, "tmax");
  const pts = seriesOn(obs, "tmax", range[0], range[1]);
  const valid = finite(pts.map((x) => x.y));
  const thr = p?.heat_c ?? null;
  const avg = valid.length ? valid.reduce((a, x) => a + x, 0) / valid.length : null;
  const hot = thr != null && valid.length ? valid.filter((v) => v > thr).length : null;
  let normal: number | null = null;
  if (thr != null && season && c.cal) {
    const counts = hotDayCounts(c.clim, (y) => seasonForYear(c.cal!, y), range[1] - range[0] + 1, thr);
    if (counts.length >= 10) normal = median(counts);
  }
  const kpis = el("div", { class: "kpis" });
  if (avg != null) kpis.append(el("div", { class: "kpi" }, el("div", { class: "kpi-v" }, fmt.c(avg)), el("div", { class: "kpi-l" }, "average daily maximum")));
  if (hot != null) {
    kpis.append(el("div", { class: "kpi" },
      el("div", { class: "kpi-v" }, String(hot), el("span", { class: "kpi-u" }, normal != null ? ` / normal ${Math.round(normal)}` : "")),
      el("div", { class: "kpi-l" }, `hot days above ${thr} °C`)));
  }
  b.body.append(kpis);
  const lines = [{ label: "Daily maximum", color: T.this, points: pts }];
  if (cmp && season) {
    const ix = indexOf(cmp.data);
    lines.push({ label: `Season ${cmp.season.year}`, color: T.cmp, points: pts.map((pt) => {
      const i = ix.get(cmp.season.plant + (pt.day - season.plant));
      return { day: pt.day, y: i === undefined ? null : cmp.data.tmax[i] };
    }) });
  }
  b.body.append(legend([
    { label: "Daily maximum", color: T.this, kind: "line" },
    ...(cmp ? [{ label: `Season ${cmp.season.year}`, color: T.cmp, kind: "line" as const }] : []),
    { label: "Normal range", color: T.band, kind: "band" },
  ]));
  chart(b.body, (w) => timeChart({
    width: w, height: 220, yLabel: "°C", unit: "°C", band: bandOnDates(bands, range[0], range[1]), lines,
    hline: thr != null ? { y: thr, label: `${thr} °C` } : undefined,
  }));
  b.body.append(more("Data table", tableView(["Date", "Tmax (°C)", "Tmin (°C)"], pts.map((pt, i) => {
    const tmin = seriesOn(obs, "tmin", range[0], range[1])[i]?.y ?? null;
    return [fromDay(pt.day), r1(pt.y), r1(tmin)];
  }))));
  b.info(
    `Daily maximum temperature from ${fmtDay(range[0])} to ${fmtDay(range[1])} against the 1991–2020 normal range (10th–90th percentile, ±7-day window).`,
    thr != null ? `Hot-day threshold for ${cropLabel.toLowerCase()}: ${thr} °C. ${p?.heat_ref ? c.params.references[p.heat_ref] : ""}` : "No heat threshold is set for this crop.",
    el("p", { class: "src" }, "ERA5 2 m temperature via Open-Meteo."));
  return { hot, normal, avg };
}

// =====================================================================
function renderOther(b: Block, c: RenderCtx, obs: Daily, range: [Day, Day], asOf: Day): number | null {
  const T = theme();
  const g = el("div", { class: "grid3" });
  b.body.append(g);
  const panels: { v: "rh" | "et0" | "sm"; title: string; unit: string; scale: number; ico: string }[] = [
    { v: "sm", title: "Soil moisture", unit: "%", scale: 100, ico: "soil" },
    { v: "rh", title: "Humidity", unit: "%", scale: 1, ico: "cloud" },
    { v: "et0", title: "Evaporation demand (ET₀)", unit: "mm/day", scale: 1, ico: "sun" },
  ];
  let smPct: number | null = null;
  const at = Math.min(asOf, range[1]);
  const ix = indexOf(obs);
  for (const pn of panels) {
    const pts = seriesOn(obs, pn.v, range[0], range[1], pn.scale);
    const cell = el("div", { class: "mini" });
    g.append(cell);
    const i = ix.get(at);
    const raw = i === undefined ? null : obs[pn.v][i];
    const pct = raw != null ? doyPercentile(c.clim, pn.v, at, raw) : null;
    if (pn.v === "sm") smPct = pct;
    cell.append(el("div", { class: "mini-head" }, icon(pn.ico, 18), el("span", {}, pn.title)),
      el("div", { class: "mini-v" }, raw != null ? `${(raw * pn.scale).toFixed(pn.v === "et0" ? 1 : 0)} ${pn.unit}` : "–"),
      pct != null ? meter(pct, pn.v === "et0" ? "Low" : "Dry", pn.v === "et0" ? "High" : pn.v === "rh" ? "Humid" : "Wet", 170) : note("Not available here."));
    if (!finite(pts.map((x) => x.y)).length) continue;
    const bands = doyBands(c.clim, pn.v).map((bd) => bd && ({ p10: bd.p10 * pn.scale, p50: bd.p50 * pn.scale, p90: bd.p90 * pn.scale }));
    chart(cell, (w) => timeChart({ width: w, height: 150, yLabel: pn.unit, unit: pn.unit, band: bandOnDates(bands, range[0], range[1]), lines: [{ label: pn.title, color: T.this, points: pts }] }));
  }
  b.info(
    `Values on ${fmtDay(at)} and the season so far, against the 1991–2020 normal range for the time of year. Soil moisture is the modelled water content of the top 100 cm (m³/m³ shown as %), not a field measurement. ET₀ is the FAO-56 reference evapotranspiration: how much water the air can take from a well-watered grass field.`,
    el("p", { class: "src" }, "ERA5 via Open-Meteo."));
  return smPct;
}

// =====================================================================
function renderForecast(b: Block, c: RenderCtx, days: EnsembleDay[], p: CropParams | null) {
  const T = theme();
  const rows = days.map((d) => ({
    day: d.day,
    p10: quantile(d.members.precip, 0.1), p50: quantile(d.members.precip, 0.5), p90: quantile(d.members.precip, 0.9),
    t10: quantile(d.members.tmax, 0.1), t50: quantile(d.members.tmax, 0.5), t90: quantile(d.members.tmax, 0.9),
  }));
  const total = rows.reduce((a, r) => a + r.p50, 0);
  const wetDays = rows.filter((r) => r.p50 >= 1).length;
  const thr = p?.heat_c ?? null;
  const hotDays = thr != null ? rows.filter((r) => r.t50 > thr).length : 0;
  b.body.append(el("div", { class: "kpis" },
    el("div", { class: "kpi" }, el("div", { class: "kpi-v" }, fmt.mm(total)), el("div", { class: "kpi-l" }, `rain expected · ${wetDays} wet day${wetDays === 1 ? "" : "s"}`)),
    thr != null ? el("div", { class: "kpi" }, el("div", { class: "kpi-v" }, String(hotDays)), el("div", { class: "kpi-l" }, `days above ${thr} °C`)) : null));
  b.body.append(forecastStrip(rows.map((r) => ({ date: toDate(r.day), rain: r.p50, rainHi: r.p90, tmax: r.t50, hot: thr != null && r.t50 > thr }))));

  const clim = doyBands(c.clim, "tmax");
  const g = el("div", { class: "grid2" });
  const c1 = el("div", {}, el("h3", {}, "Daily rain"), legend([{ label: "Median", color: T.this, kind: "dot" }, { label: "Likely range (10–90%)", color: T.ink2, kind: "line" }]));
  const c2 = el("div", {}, el("h3", {}, "Daily maximum temperature"), legend([
    { label: "Median", color: T.this, kind: "line" }, { label: "Normal", color: T.band, kind: "line" }, { label: "Likely range", color: T.band, kind: "band" }]));
  g.append(c1, c2);
  const details = more("Detailed charts and table", g);
  b.body.append(details);
  chart(c1, (w) => forecastRain(w, rows));
  chart(c2, (w) => timeChart({
    width: w, height: 200, yLabel: "°C", unit: "°C",
    band: rows.map((r) => ({ day: r.day, lo: r.t10, mid: r.t50, hi: r.t90 })), bandLabel: "Likely range",
    lines: [
      { label: "Median", color: T.this, points: rows.map((r) => ({ day: r.day, y: r.t50 })) },
      { label: "Normal", color: T.band, points: rows.map((r) => ({ day: r.day, y: clim[dayOfYear(r.day)]?.p50 ?? null })) },
    ],
    hline: thr != null ? { y: thr, label: `${thr} °C` } : undefined,
  }));
  details.append(tableView(["Date", "Rain median (mm)", "Rain 10–90% (mm)", "Tmax median (°C)", "Tmax 10–90% (°C)"],
    rows.map((r) => [fromDay(r.day), r1(r.p50), `${r1(r.p10)}–${r1(r.p90)}`, r1(r.t50), `${r1(r.t10)}–${r1(r.t90)}`])));
  b.info(
    "Each day shows the middle forecast (median) of the ensemble: the drop and number give rain in mm, the bar height shows rain, and the pale bar the upper likely amount (90th percentile). Days above the crop's heat threshold are marked.",
    el("p", { class: "src" }, `ECMWF IFS 0.25° ensemble (${days[0]?.members.precip.length ?? 0} members) via Open-Meteo, updated daily.`));
}

function renderSeasonal(b: Block, months: SeasonalMonth[], target: Season | null, tp: StagePlan | null) {
  let m0: Day | null = null;
  let m1: Day | null = null;
  if (target && tp) { m0 = target.plant + tp.bounds[1]; m1 = target.plant + tp.bounds[2] - 1; }
  const items = months.map((m) => {
    const start = toDay(m.month + "-01");
    const inStage = m0 != null && m1 != null && start <= m1 && start + 30 >= m0;
    return { label: `${monthName(Number(m.month.slice(5, 7)))} ${m.month.slice(2, 4)}`, pct: m.precipPct, tAnom: m.tAnom, inStage };
  });
  b.body.append(outlookTiles(items));
  b.body.append(legend([
    { label: "Drier than normal", color: theme().dry, kind: "band" },
    { label: "Wetter than normal", color: theme().wet, kind: "band" },
  ]));
  b.body.append(more("Data table", tableView(["Month", "Rain (mm)", "Rain vs model normal", "Temperature vs model normal"], months.map((m) => [
    m.month, m.precipMm != null ? Math.round(m.precipMm) : null,
    m.precipPct != null ? `${m.precipPct > 0 ? "+" : ""}${Math.round(m.precipPct)}%` : null,
    m.tAnom != null ? `${m.tAnom > 0 ? "+" : ""}${m.tAnom.toFixed(1)} °C` : null,
  ]))));
  b.info(
    "Each tile compares the forecast month's rain with the forecast model's own normal: the arrow and % show drier or wetter, the small number the temperature difference. Tiles marked \"flowering\" overlap the crop's most water-sensitive stage" + (m0 != null ? ` (${fmtDay(m0)} – ${fmtDay(m1!)})` : "") + ".",
    "Seasonal forecasts show the tendency over a wide area. They are often wrong at a single place.",
    el("p", { class: "src" }, "ECMWF SEAS5, 51-member ensemble mean and anomaly vs SEAS5 hindcast climatology, via Open-Meteo."));
}

// =====================================================================
function renderAfter(b: Block, c: RenderCtx, obs: Daily, D: Day) {
  const T = theme();
  const last = lastEra5Day();
  const end16 = Math.min(D + 16, last);
  if (end16 <= D) { b.body.append(note("No observations after this date yet.")); return; }
  const ix = indexOf(obs);
  let rain = 0;
  for (let d = D + 1; d <= end16; d++) rain += obs.precip[ix.get(d) ?? -1] ?? 0;
  const sums: number[] = [];
  const cix = indexOf(c.clim);
  for (let y = 1991; y <= 2020; y++) {
    const start = toDay(`${y}-${fromDay(D + 1).slice(5)}`.replace("-02-29", "-02-28"));
    let s = 0; let ok = true;
    for (let k = 0; k < end16 - D; k++) { const v = c.clim.precip[cix.get(start + k) ?? -1]; if (v == null) { ok = false; break; } s += v; }
    if (ok) sums.push(s);
  }
  const pr = sums.length ? percentileRank(sums, rain) : null;
  b.body.append(el("div", { class: "kpis" }, el("div", { class: "kpi" },
    el("div", { class: "kpi-v" }, fmt.mm(rain)),
    el("div", { class: "kpi-l" }, `rain in the next ${end16 - D} days${sums.length ? ` · normal ${fmt.mm(median(sums))}` : ""}`),
    pr != null ? meter(pr, "Dry", "Wet", 200) : null)));
  chart(b.body, (w) => timeChart({
    width: w, height: 190, yLabel: "°C", unit: "°C", band: bandOnDates(doyBands(c.clim, "tmax"), D + 1, end16),
    lines: [{ label: "Daily maximum", color: T.this, points: seriesOn(obs, "tmax", D + 1, end16) }],
  }));
  const months = monthlyVsNormal(obs, c.clim, D + 1, Math.min(D + 214, last));
  if (months.length) {
    b.body.append(el("h3", {}, "Following months: rain vs normal"));
    b.body.append(outlookTiles(months.map((m) => ({ label: `${monthName(m.m)} ${String(m.y).slice(2)}`, pct: m.pct, tAnom: null }))));
    b.body.append(more("Data table", tableView(["Month", "Rain (mm)", "1991–2020 mean (mm)", "Departure"], months.map((m) => [`${m.y}-${String(m.m).padStart(2, "0")}`, Math.round(m.rain), Math.round(m.normal), m.pct != null ? `${Math.round(m.pct)}%` : null]))));
  }
  b.info("What was observed after the selected date: rain and daily maximum temperature for 16 days, then monthly rain compared with the 1991–2020 mean.", el("p", { class: "src" }, "ERA5 via Open-Meteo."));
}

// =====================================================================
function ensoTile(e: EnsoData | null, D: Day, current: boolean): HTMLElement | null {
  if (!e) return null;
  const { y, m } = ymd(D);
  const val = current ? e.latest.value : indexValue(e, y, m);
  if (val == null) return null;
  const phase = val >= 0.5 ? "El Niño" : val <= -0.5 ? "La Niña" : "Neutral";
  const tone: Tone = val >= 1.5 || val <= -1.5 ? "concern" : phase !== "Neutral" ? "watch" : "good";
  const cap = current && e.run_in_progress
    ? `${e.run_in_progress.seasons_so_far} season${e.run_in_progress.seasons_so_far > 1 ? "s" : ""} in a row`
    : current ? "Pacific Ocean index" : `in ${monthName(m)} ${y}`;
  return tile({ ico: "wave", title: phase === "Neutral" ? "ENSO" : phase, value: `${val > 0 ? "+" : ""}${val.toFixed(1)} °C`, caption: cap, tone, target: "enso" });
}

function renderEnso(b: Block, c: RenderCtx, D: Day, current: boolean, season: Season | null, onComposite: (x: Composite | null) => void) {
  const e = c.enso;
  if (!e) { b.body.append(note("ENSO data not available yet.", "note error")); return; }
  const T = theme();
  const [y0, m0] = e.start.split("-").map(Number);
  const series = e.values.map((v, i) => ({ date: new Date(Date.UTC(y0, m0 - 1 + i, 15)), v })).filter((x): x is { date: Date; v: number } => x.v != null);
  const eps = e.episodes.map((ep) => ({ type: ep.type, start: new Date(ep.start + "-01"), end: new Date(ep.end + "-28") }));
  const { y, m } = ymd(D);
  const val = current ? e.latest.value : indexValue(e, y, m);
  const phaseThen = episodeMonths(e).get(`${y}-${m}`);

  // Status row: big value + phase badge + SEAS5 mini outlook
  const phase = val == null ? "–" : val >= 0.5 ? "El Niño" : val <= -0.5 ? "La Niña" : "Neutral";
  const status = el("div", { class: "kpis" },
    el("div", { class: "kpi" },
      el("div", { class: "kpi-v" }, val != null ? `${val > 0 ? "+" : ""}${val.toFixed(2)} °C` : "–"),
      el("div", { class: "kpi-l" }, `${e.index} ${current ? e.latest.month : `${y}-${String(m).padStart(2, "0")}`}`),
      el("span", { class: `badge ${phase === "El Niño" ? "nino" : phase === "La Niña" ? "nina" : "neutral"}` }, phase)));
  if (current && e.seas5_nino34?.months?.length) {
    const s5 = e.seas5_nino34;
    const row = el("div", { class: "nino-row" });
    s5.months.forEach((mo, i) => {
      const v = s5.anomaly_c[i];
      row.append(el("div", { class: `nino-m ${v != null && v >= 0.5 ? "warm" : v != null && v <= -0.5 ? "cool" : ""}` },
        el("div", { class: "om" }, monthName(Number(mo.slice(5)))), el("div", { class: "ov" }, v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}` : "–")));
    });
    status.append(el("div", { class: "kpi" }, el("div", { class: "kpi-l" }, "Model outlook, Niño-3.4 (°C)"), row));
  }
  b.body.append(status);
  b.body.append(legend([{ label: e.index, color: T.ink2, kind: "line" }, { label: "El Niño", color: T.nino, kind: "band" }, { label: "La Niña", color: T.nina, kind: "band" }]));
  chart(b.body, (w) => ensoTimeline(w, series, eps, current ? undefined : toDate(D)));

  b.info(
    `The ${e.index === "RONI" ? "Relative Oceanic Niño Index (RONI)" : "Oceanic Niño Index (ONI)"} measures how warm the central Pacific is. El Niño: +0.5 °C or more for five overlapping seasons in a row; La Niña: −0.5 °C or less.` +
      (current && e.run_in_progress ? ` Now: ${e.run_in_progress.seasons_so_far} season${e.run_in_progress.seasons_so_far > 1 ? "s" : ""} in a row at ${e.run_in_progress.type === "El Nino" ? "El Niño" : "La Niña"} level.` : "") +
      (!current ? (phaseThen ? ` On the selected date an official ${phaseThen === "El Nino" ? "El Niño" : "La Niña"} episode was under way.` : " On the selected date there was no official episode.") : ""),
    e.seas5_nino34 ? e.seas5_nino34.description : "",
    el("p", {}, "Official outlooks: ",
      el("a", { href: "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml" }, "NOAA CPC"), " · ",
      el("a", { href: "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/" }, "IRI")),
    el("p", { class: "src" }, `NOAA CPC ${e.index}, ${e.index_source}, updated ${e.generated_utc}.`));

  // Local composites
  const cal: Calendar = c.cal ?? (() => {
    const start = toDay(`2001-${String(m).padStart(2, "0")}-01`);
    return { plantDoy: dayOfYear(start), maturityDoy: ((dayOfYear(start) + 182 - 1) % 365) + 1 };
  })();
  const what = c.cal ? `${c.params.ggcmi_labels[c.cropKey!.slice(0, 3)]} season (${doyLabel(cal.plantDoy)} – ${doyLabel(cal.maturityDoy)})`
    : `six months from ${monthName(m)}`;
  const holder = el("div", { class: "history" });
  const btn = el("button", { class: "cta", type: "button" }, icon("chart", 18), el("span", {}, "Show past El Niño seasons here"));
  holder.append(el("h3", {}, "Past El Niño seasons here"), btn, el("p", { class: "muted small" }, `${what}, every year since 1950`));
  b.body.append(holder);
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.lastElementChild!.textContent = "Loading 75 years of data…";
    try {
      c.setStatus(S.status.enso);
      const [a1, a2] = await Promise.all([
        era5Daily(c.state.lat!, c.state.lon!, toDay("1950-01-01"), toDay("1990-12-31"), ["precip", "tmax"], (msg) => c.setStatus(msg)),
        era5Daily(c.state.lat!, c.state.lon!, toDay("2021-01-01"), lastEra5Day(), ["precip", "tmax"], (msg) => c.setStatus(msg)),
      ]);
      if (!c.alive()) return;
      const all = mergeDaily([a1.data, c.clim, a2.data]);
      const seasonFor = (yy: number) => seasonForYear(cal, yy);
      let lastY = ymd(lastEra5Day()).y;
      while (seasonFor(lastY).harvest > lastEra5Day()) lastY--;
      const comp = composite(seasonTotals(all, seasonFor, 1950, lastY), seasonFor, e);
      holder.replaceChildren(el("h3", {}, "Past El Niño seasons here"));
      if (!comp) { holder.append(note("Not enough complete seasons to compare.")); return; }
      renderComposite(b, holder, comp, what, season ? [season.year, ...(c.state.cmp ? [c.state.cmp] : [])] : []);
      c.setStatus(S.status.done);
      onComposite(comp);
    } catch (err) {
      btn.disabled = false;
      btn.lastElementChild!.textContent = "Retry";
      c.setStatus(`El Niño history failed: ${(err as Error).message}`, true);
    }
  });
}

const pFmt = (p: number) => (p < 0.001 ? "<0.001" : p.toFixed(3));

function renderComposite(b: Block, holder: HTMLElement, comp: Composite, what: string, highlight: number[]) {
  const T = theme();
  const n = comp.byPhase["El Nino"];
  const neu = comp.byPhase["Neutral"];
  const sig = comp.pRainNinoVsNeutral < 0.05;
  if (n.n > 0) {
    holder.append(el("div", { class: "picto-row" },
      el("div", { class: "kpi-v" }, `${n.drierCount} of ${n.n}`),
      el("div", { class: "kpi-l" }, "El Niño seasons were drier than normal"),
      pictogram(n.n, n.drierCount, T.dry, T.axis, `${n.drierCount} of ${n.n} El Niño seasons drier than normal`),
      el("span", { class: `badge ${sig ? "sig" : "nsig"}` }, sig ? "Clear pattern" : "Not a clear pattern")));
  } else holder.append(note("No El Niño season in the record for this period."));

  const g = el("div", { class: "grid2" });
  const c1 = el("div", {}, el("h3", {}, "Season rain vs normal"));
  const c2 = el("div", {}, el("h3", {}, "Season heat vs trend"));
  g.append(c1, c2);
  holder.append(legend([{ label: "El Niño", color: T.nino, kind: "dot" }, { label: "Neutral", color: T.neutral, kind: "dot" }, { label: "La Niña", color: T.nina, kind: "dot" }, { label: "Median", color: T.ink, kind: "line" }]));
  holder.append(g);
  chart(c1, (w) => compositeDots(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.rainPct })), "%", "% vs normal", highlight));
  chart(c2, (w) => compositeDots(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.tempAnom })), " °C", "°C", highlight));
  holder.append(more("Data table", tableView(["Season", "Phase", "Rain (mm)", "Rain vs normal", "Tmax vs trend (°C)"],
    [...comp.points].reverse().map((p) => [String(p.year), p.phase === "El Nino" ? "El Niño" : p.phase === "La Nina" ? "La Niña" : "Neutral", Math.round(p.rain), `${Math.round(p.rainPct)}%`, r1(p.tempAnom)]))));
  const dir = n.medianRainPct < neu.medianRainPct ? "drier" : "wetter";
  b.info(
    el("h4", {}, "Past El Niño seasons"),
    sig
      ? `In the ${what}, El Niño seasons were ${dir} than neutral seasons: median ${fmt.pct(n.medianRainPct)} vs ${fmt.pct(neu.medianRainPct)} against the 1991–2020 normal (rank test p = ${pFmt(comp.pRainNinoVsNeutral)}).`
      : `In the ${what}, El Niño seasons were not clearly different from neutral seasons: median ${fmt.pct(n.medianRainPct)} vs ${fmt.pct(neu.medianRainPct)} (rank test p = ${pFmt(comp.pRainNinoVsNeutral)}). The difference could be chance.`,
    `Heat: season mean daily maximum, El Niño ${fmt.dc(n.medianTempAnom)} vs neutral ${fmt.dc(neu.medianTempAnom)} after removing the warming trend (p = ${pFmt(comp.pTempNinoVsNeutral)}).`,
    `Seasons ${comp.firstYear}–${comp.lastYear}. A season counts as El Niño or La Niña when more than half of it falls in an official NOAA episode. Normal = 1991–2020 average (${Math.round(comp.normalRain)} mm). Each dot is one season; outlined dots are the seasons you selected. Past seasons are not a forecast: every El Niño is different.`,
    el("p", { class: "src" }, "ERA5 via Open-Meteo; ENSO episodes from NOAA CPC."));
}

// =====================================================================
const ADVICE_ICON: [RegExp, string][] = [[/rain|dry|water/i, "drop"], [/heat/i, "thermo"], [/soil/i, "soil"], [/el niño/i, "wave"], [/heavy/i, "rain"]];

function renderAdvice(b: HTMLElement, items: Advice[]) {
  if (!items.length) {
    b.append(el("div", { class: "ok-card" }, icon("check", 26), el("div", {}, el("strong", {}, "Nothing unusual right now"), el("div", { class: "muted" }, "Continue normal practice."))));
    return;
  }
  const list = el("div", { class: "acards" });
  for (const a of items) {
    const ico = (a.title.match(/heavy/i) ? "rain" : ADVICE_ICON.find(([re]) => re.test(a.title))?.[1]) ?? "alert";
    const why = el("div", { class: "a-why", hidden: "" }, el("p", {}, a.trigger), el("p", { class: "src" }, a.source));
    const tgl = el("button", { class: "info-btn sm", type: "button", "aria-expanded": "false", "aria-label": "Why?" }, icon("info", 18));
    tgl.addEventListener("click", () => {
      const open = tgl.getAttribute("aria-expanded") === "true";
      tgl.setAttribute("aria-expanded", String(!open));
      why.hidden = open;
    });
    list.append(el("div", { class: "acard" },
      el("div", { class: "a-ico" }, icon(ico, 24)),
      el("div", { class: "a-main" }, el("div", { class: "a-t" }, a.title), el("div", { class: "a-do" }, a.action), why),
      tgl));
  }
  b.append(list);
}
