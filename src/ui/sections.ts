import { Day, dayOfYear, fmtDay, fromDay, monthName, toDate, toDay, todayDay, ymd } from "../lib/dates";
import { CropParamFile, LocalCrops } from "../api/static";
import { EnsembleDay, GridInfo, SeasonalMonth, era5Daily, era5Windows, ensembleForecast, lastEra5Day, mergeDaily, seasonalMonthly } from "../api/openmeteo";
import {
  Band, Daily, cumulative, cumulativeRainBand, doyBands, doyPercentile, hotDayCounts, indexOf,
  CLIM_END, CLIM_START, monthlyVsNormal, sameDatesNormal, seasonTotals, waterBalance,
} from "../calc/climate";
import { Calendar, CropParams, Season, seasonForYear, seasonStatus, stageIndex, stagePlan, StagePlan } from "../calc/season";
import { Composite, EnsoData, PhaseImpact, composite, ensoState, indexValue, phaseImpact } from "../calc/enso";
import { finite, median, percentileRank, quantile } from "../calc/stats";
import { Advice, buildAdvice } from "../calc/advice";
import { S } from "../strings";
import { cropName } from "../lib/cropnames";
import { Sec, chart, el, fmt, more, note, resetCharts, section, tabs } from "./dom";
import { beeswarm, ensoArea, keys, monthBars, r1, sparkline, tableView, theme, timeChart } from "./charts";
import { CalRow, cropCalendar, forecastList, metric, needBars, outlookStrip, pctBar, pctStatus, seasonLine, statusTag } from "./visuals";
import type { State } from "../main";
import { ComingView, forecastVsNormal, impactSkeleton, renderComing, renderImpact } from "./impact";

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
  fields: HTMLElement;           // crop and comparison selects (owned by main.ts)
  details: HTMLElement;          // right-hand area below the map: tabs with charts
  alive: () => boolean;
  setStatus: (m: string | null, err?: boolean) => void;
}

const MIN_CROPLAND_HA = 50;
type Line = { label: string; color: string; points: { day: Day; y: number | null }[]; width?: number };
const STAGE_LABELS = ["Establishment", "Growth", "Flowering", "Ripening"];

export async function renderReport(c: RenderCtx) {
  resetCharts();
  const root = c.root;
  root.replaceChildren();
  c.details.replaceChildren();
  const today = todayDay();
  const last = lastEra5Day();
  const D = Math.min(c.state.date, today);
  const current = D >= today - 7;
  const asOf = current ? last : D;

  const code = c.cropKey?.slice(0, 3) ?? null;
  const cropLabel = code ? c.params.ggcmi_labels[code] ?? code : "";
  const p: CropParams | null = code ? c.params.params[c.params.ggcmi_to_param[code]] ?? null : null;

  // ---------------------------------------------------------------- header
  root.append(
    el("div", { class: "eyebrow" }, current ? "Conditions now" : `Looking back · ${fmtDay(D)}`),
    el("h1", { class: "place", id: "place-name" }, c.state.name ?? `${c.state.lat!.toFixed(2)}°, ${c.state.lon!.toFixed(2)}°`),
    el("div", { class: "meta" },
      c.state.name ? el("span", {}, `${c.state.lat!.toFixed(2)}°, ${c.state.lon!.toFixed(2)}°`) : null,
      el("span", {}, `${Math.round(c.grid.elevation).toLocaleString("en")} m`),
      el("span", {}, current ? `Observed to ${fmtDay(last)}` : `As of ${fmtDay(D)}`)),
    c.fields);

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

  // Season line
  if (season && c.cal) {
    const shown = inSeason ? season : nextSeason!;
    const shownPlan = p?.stages ? stagePlan(p.stages, shown.length) : null;
    const title = inSeason
      ? `${cropLabel} · ${plan ? STAGE_LABELS[stageIndex(plan, dayOfSeason)].toLowerCase() : "in season"}`
      : `${cropLabel} · next season`;
    const sub = inSeason ? `Day ${dayOfSeason} of ${season.length}` : `Sowing in ${nextSeason!.plant - asOf} days`;
    const box = el("div", { class: "seasonline" }, el("div", { class: "sl-top" }, el("span", { class: "sl-title" }, title), el("span", { class: "sl-sub" }, sub)));
    root.append(box);
    chart(box, (w) => seasonLine({ plant: shown.plant, harvest: shown.harvest, bounds: shownPlan?.bounds ?? null, names: STAGE_LABELS, today: inSeason ? asOf : null }, w));
    box.append(el("div", { class: "sl-top", style: "margin:4px 0 0" },
      el("span", { class: "sl-sub" }, `Sow ${fmtDay(shown.plant)}`), el("span", { class: "sl-sub" }, `Harvest ${fmtDay(shown.harvest)}`)));
  }
  if (!current) root.append(el("div", { class: "banner" }, el("strong", {}, "Past date. "), "Forecasts are replaced by what was observed afterwards."));

  // Summary metrics (filled progressively)
  const metrics = el("div", { class: "metrics" });
  root.append(metrics);
  const slot = () => { const s = el("div", { class: "metric" }, el("div", { class: "sk", style: "height:14px;width:60%" }), el("div", { class: "sk", style: "height:28px;width:40%;margin-top:8px" })); metrics.append(s); return s; };
  const mRain = slot(), mSoil = slot(), mHeat = slot(), mEnso = slot();
  const fixRows = () => {
    const items = [...metrics.children] as HTMLElement[];
    items.forEach((m, i) => m.classList.toggle("last-row", i >= items.length - (items.length % 2 === 0 ? 2 : 1)));
  };

  // El Nino / La Nina impact and the coming weeks: shown on their own when the
  // date falls in (or just before) an ENSO event
  const est = c.enso ? ensoState(c.enso, D, current) : null;
  const impactBox = el("div", { class: "ix" });
  if (est) { root.append(impactBox); impactSkeleton(impactBox, est, current); }
  const comingBox = el("div", { class: "ix" });
  if (current) root.append(comingBox);

  // Recommendations placeholder
  const recs = el("div", { class: "recs" });
  if (current) root.append(recs);

  // ---------------------------------------------------------------- data
  c.setStatus(S.status.season);
  const from: Day = season ? Math.min(season.plant, asOf - 60) : asOf - 150;
  const to: Day = current ? last : Math.min(last, Math.max(season?.harvest ?? D, D + 214, est && !inSeason && nextSeason ? nextSeason.harvest : D));
  const obs = (await era5Daily(c.state.lat!, c.state.lon!, from, to, ["precip", "tmax", "tmin", "et0", "rh", "sm"], (m) => c.setStatus(m))).data;
  if (!c.alive()) return;
  let cmp: { season: Season; data: Daily } | null = null;
  if (c.cal && c.state.cmp) {
    const cs = seasonForYear(c.cal, c.state.cmp);
    cmp = { season: cs, data: (await era5Daily(c.state.lat!, c.state.lon!, cs.plant, cs.harvest, ["precip", "tmax"])).data };
    if (!c.alive()) return;
  }

  // ---------------------------------------------------------------- tabs
  const labels = current ? ["Season", "15 days", "Outlook", "El Niño"] : ["Season", "Afterwards", "El Niño"];
  const panels = tabs(c.details, labels);
  const [tSeason, tNext, tOutlook] = panels;
  const tEnso = panels[panels.length - 1];

  // Season tab
  const crops = section(tSeason, "Crops grown here");
  renderCrops(crops, c, asOf);

  const range: [Day, Day] = season ? [season.plant, Math.min(season.harvest, asOf)] : [asOf - 120, asOf];
  let rainPct: number | null = null;
  let gapMm: number | null = null;
  if (c.cal && season) {
    const w = renderWater(section(tSeason, inSeason ? "Rain since sowing" : "Last season's rain"), c, season, obs, asOf, p, cmp, cropLabel);
    rainPct = w.percentile;
    gapMm = w.gap;
    const st = pctStatus(w.percentile);
    mRain.replaceWith(metric({
      label: inSeason ? "Rain since sowing" : "Last season's rain",
      value: w.pctOfNormal != null ? `${Math.round(w.pctOfNormal)}%` : w.total != null ? `${Math.round(w.total)}` : "–",
      unit: w.pctOfNormal != null ? undefined : "mm",
      ctx: w.total != null ? `${w.pctOfNormal != null ? "of normal · " : ""}${fmt.mm(w.total)} since ${fmtDay(season.plant).replace(/ \d{4}$/, "")}` : undefined,
      viz: w.percentile != null ? pctBar(w.percentile, 190) : null,
      status: statusTag(st.s, st.word),
    }));
  } else {
    const recent = recentRain(obs, c.clim, asOf, 90);
    const st = pctStatus(recent.pct);
    mRain.replaceWith(metric({ label: "Rain, last 90 days", value: `${Math.round(recent.total)}`, unit: "mm", ctx: recent.normal != null ? `normal ${fmt.mm(recent.normal)}` : undefined, viz: recent.pct != null ? pctBar(recent.pct, 190) : null, status: statusTag(st.s, st.word) }));
  }

  const heat = renderTemp(section(tSeason, "Heat"), c, obs, range, p, season, cmp, cropLabel);
  mHeat.replaceWith(heat.hot != null
    ? metric({
      label: `Days above ${p!.heat_c} °C`, value: String(heat.hot), unit: "days",
      ctx: heat.normal != null ? `normal ${Math.round(heat.normal)} for these dates` : "this season",
      status: heat.normal != null ? statusTag(heat.hot > heat.normal * 1.5 && heat.hot >= 5 ? "bad" : heat.hot > heat.normal ? "warn" : "good", heat.hot > heat.normal ? "More than normal" : "Normal or fewer") : null,
    })
    : metric({ label: "Average daily maximum", value: heat.avg != null ? heat.avg.toFixed(1) : "–", unit: "°C", ctx: season ? "this season" : "last 120 days" }));

  const smPct = renderSoilAir(section(tSeason, "Soil and air"), c, obs, range, asOf);
  if (smPct.pct != null) {
    const st = pctStatus(smPct.pct, "Drier than normal", "Wetter than normal");
    mSoil.replaceWith(metric({ label: "Soil moisture", value: `${Math.round(smPct.value! * 100)}`, unit: "% vol", ctx: `${fmt.ord(smPct.pct)} percentile for the date`, viz: pctBar(smPct.pct, 190), status: statusTag(st.s, st.word) }));
  } else mSoil.remove();

  // ENSO metric
  const ensoM = ensoMetric(c.enso, D, current);
  if (ensoM) mEnso.replaceWith(ensoM); else mEnso.remove();
  fixRows();

  // Forecasts or what happened next
  let fc: EnsembleDay[] | null = null;
  let seas: SeasonalMonth[] | null = null;
  let fc15: ComingView["fc15"] = null;
  if (current) {
    c.setStatus(S.status.forecast);
    const [f, s] = await Promise.allSettled([ensembleForecast(c.state.lat!, c.state.lon!), seasonalMonthly(c.state.lat!, c.state.lon!)]);
    if (!c.alive()) return;
    const fsec = section(tNext, "Next 15 days");
    if (f.status === "fulfilled") { fc = f.value.days; renderForecast(fsec, c, fc, p); }
    else fsec.body.append(note(`Forecast unavailable: ${(f.reason as Error).message}`, "note error"));
    const osec = section(tOutlook, "Rain outlook, next months");
    if (s.status === "fulfilled") { seas = s.value; renderOutlook(osec, seas, inSeason ? season : nextSeason, inSeason ? plan : seasonPlanFor(nextSeason, p)); }
    else osec.body.append(note(`Seasonal forecast unavailable: ${(s.reason as Error).message}`, "note error"));
    if (fc?.length) fc15 = forecastVsNormal(fc, sameDatesNormal(c.clim, fc[0].day, fc[fc.length - 1].day, p?.heat_c ?? null), p?.heat_c ?? null);
  } else {
    renderAfter(section(tNext, "What happened next"), c, obs, D);
  }

  // Recommendations
  let impact: PhaseImpact | null = null;
  let impactLoading = !!est;
  const renderComingNow = () => { if (current) renderComing(comingBox, { fc, fc15, heatC: p?.heat_c ?? null, seasonal: seas, impact, state: est, enso: c.enso }); };
  const renderRecs = () => {
    if (!current) return;
    recs.replaceChildren(el("div", { class: "recs-h" }, el("h2", {}, "What to do")));
    if (!c.cal || !season) { recs.append(note("Guidance needs a crop calendar, which is not available here.")); return; }
    const target = inSeason ? season : nextSeason!;
    const items = buildAdvice({
      cropLabel, season: target, inSeason, today,
      plan: p?.stages ? stagePlan(p.stages, target.length) : null,
      heatC: p?.heat_c ?? null, heatRef: p?.heat_ref ?? null,
      rainPercentile: inSeason ? rainPct : null, gapMm: inSeason ? gapMm : null,
      smPercentile: smPct.pct, forecast: fc, seasonal: seas, fc15,
      enso: est ? { ...est, impact, loading: impactLoading } : null, references: c.params.references,
    });
    renderAdvice(recs, items);
  };

  // Per-season history 1950 to today, loaded once and shared by the impact block
  // and the El Nino tab.
  const hcal = historyCal(c, D);
  const seasonForH = (yy: number) => seasonForYear(hcal, yy);
  let histP: Promise<History> | null = null;
  const loadHistory = (): Promise<History> => (histP ??= (async () => {
    c.setStatus(S.status.enso);
    let lastY = ymd(lastEra5Day()).y;
    while (seasonForH(lastY).harvest > lastEra5Day()) lastY--;
    const lo = toDay(`${CLIM_START}-01-01`);
    const hi = toDay(`${CLIM_END}-12-31`);
    const ws: [Day, Day][] = [];
    for (let yy = 1950; yy <= lastY; yy++) {
      const ss = seasonForH(yy);
      // 1991-2020 seasons are already in the climatology when there is a crop calendar
      if (c.cal && ss.plant >= lo && ss.harvest <= hi) continue;
      ws.push([ss.plant, ss.harvest]);
    }
    const got = await era5Windows(c.state.lat!, c.state.lon!, ws, ["precip", "tmax"], (msg) => c.setStatus(msg));
    const all = c.cal ? mergeDaily([c.clim, got]) : got;
    c.setStatus(null);
    return { all, lastY, comp: composite(seasonTotals(all, seasonForH, 1950, lastY), seasonForH, c.enso!) };
  })().catch((err) => { histP = null; throw err; }));

  // El Nino tab
  renderEnso(tEnso, c, D, current, season, loadHistory, !!est);
  renderComingNow();
  renderRecs();

  if (est) {
    const focus: Season = c.cal ? (inSeason ? season! : nextSeason!) : seasonForH(ymd(D).y);
    loadHistory().then((h) => {
      if (!c.alive()) return;
      impactLoading = false;
      impact = h.comp ? phaseImpact(h.all, h.comp, seasonForH, c.enso!, est.phase, current ? null : focus.year) : null;
      if (impact) {
        renderImpact(impactBox, {
          enso: c.enso!, state: est, impact, all: h.all, seasonFor: seasonForH, focus, obs, obsUntil: current ? last : Math.min(last, focus.harvest),
          D, current, inSeason, what: historyWhat(c, hcal, D),
        });
      } else {
        impactBox.replaceChildren();
        section(impactBox, `${est.phase === "El Nino" ? "El Niño" : "La Niña"} impact here`).body.append(note("Not enough complete past seasons of this kind to compare."));
      }
      renderComingNow();
      renderRecs();
    }).catch((err) => {
      if (!c.alive()) return;
      impactLoading = false;
      impactBox.replaceChildren();
      section(impactBox, "El Niño impact here").body.append(note(`Could not load past seasons: ${(err as Error).message}`, "note error"));
      renderRecs();
    });
  }

  // Footer
  c.details.append(el("div", { class: "panel-foot" },
    el("p", {}, "Weather: ERA5, ECMWF IFS and SEAS5 via Open-Meteo. ENSO: NOAA CPC. Crops: CROPGRIDS, GGCMI. Water: FAO-56. ",
      el("a", { href: "methods.html" }, "Methods and sources")),
    more("Limits", el("ul", {}, ...S.limits.map((t) => el("li", {}, t))))));
  c.setStatus(null);
}

interface History { all: Daily; lastY: number; comp: Composite | null }

/** Crop calendar for the history, or six months from the selected month without one. */
function historyCal(c: RenderCtx, D: Day): Calendar {
  if (c.cal) return c.cal;
  const start = toDay(`2001-${String(ymd(D).m).padStart(2, "0")}-01`);
  return { plantDoy: dayOfYear(start), maturityDoy: ((dayOfYear(start) + 182 - 1) % 365) + 1 };
}
function historyWhat(c: RenderCtx, cal: Calendar, D: Day): string {
  return c.cal ? `${c.params.ggcmi_labels[c.cropKey!.slice(0, 3)].toLowerCase()} season, ${doyLabel(cal.plantDoy)} – ${doyLabel(cal.maturityDoy)}` : `six months from ${monthName(ymd(D).m)}`;
}

function seasonPlanFor(s: Season | null, p: CropParams | null): StagePlan | null {
  return s && p?.stages ? stagePlan(p.stages, s.length) : null;
}
function doyLabel(doy: number): string {
  const d = toDate(toDay("2001-01-01") + doy - 1);
  return `${d.getUTCDate()} ${monthName(d.getUTCMonth() + 1)}`;
}
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
function recentRain(obs: Daily, clim: Daily, asOf: Day, n: number) {
  const ix = indexOf(obs);
  let total = 0;
  for (let d = asOf - n + 1; d <= asOf; d++) total += obs.precip[ix.get(d) ?? -1] ?? 0;
  const cix = indexOf(clim);
  const sums: number[] = [];
  for (let y = 1991; y <= 2020; y++) {
    const end = toDay(`${y}-${fromDay(asOf).slice(5)}`.replace("-02-29", "-02-28"));
    let s = 0; let ok = true;
    for (let d = end - n + 1; d <= end; d++) { const v = clim.precip[cix.get(d) ?? -1]; if (v == null) { ok = false; break; } s += v; }
    if (ok) sums.push(s);
  }
  return { total, normal: sums.length ? median(sums) : null, pct: sums.length >= 10 ? percentileRank(sums, total) : null };
}

// =====================================================================
function renderCrops(s: Sec, c: RenderCtx, asOf: Day) {
  s.about("Harvested area circa 2020 from CROPGRIDS (Tang et al. 2024), aggregated to a ~28 km cell. Sowing and maturity dates from the GGCMI Phase 3 crop calendar (Jägermeyr et al. 2021), 0.5° cells. Percentages are shares of harvested area; land cropped twice a year counts twice.");
  if (!c.cropsLoaded) { s.body.append(note("Crop map not available.", "note error")); return; }
  const L = c.local;
  if (L.totalHa < MIN_CROPLAND_HA) { s.body.append(note("No cropland recorded in this cell. Weather sections still apply.")); return; }
  const rows: CalRow[] = [];
  const noCal: string[] = [];
  for (const cr of L.crops) {
    const ks = cr.ggcmi.flatMap((g) => ["rf", "ir"].map((x) => `${g}_${x}`)).filter((k) => L.calendars[k]);
    if (!ks.length) { if (cr.share >= 0.02) noCal.push(`${cropName(cr.name)} ${Math.round(cr.share * 100)}%`); continue; }
    const codes = [...new Set(ks.map((k) => k.slice(0, 3)))];
    codes.forEach((g, gi) => rows.push({
      label: codes.length > 1 ? c.params.ggcmi_labels[g] : cropName(cr.name),
      share: gi === 0 ? cr.share : null,
      windows: ks.filter((k) => k.startsWith(g)).map((k) => ({ plant: L.calendars[k][0], mature: L.calendars[k][1], irrigated: k.endsWith("_ir") })),
      selected: c.cropKey?.startsWith(g) ?? false,
    }));
  }
  const T = theme();
  s.body.append(keys([{ label: "Rainfed", color: T.sprout, kind: "band" }, { label: "Irrigated", color: T.irrig, kind: "band" }]));
  chart(s.body, (w) => cropCalendar(rows, dayOfYear(asOf), w));
  if (noCal.length) s.body.append(el("p", { class: "caption" }, `Also grown (no calendar): ${noCal.join(" · ")}`));
}

// =====================================================================
function renderWater(s: Sec, c: RenderCtx, season: Season, obs: Daily, asOf: Day, p: CropParams | null,
  cmp: { season: Season; data: Daily } | null, cropLabel: string) {
  const L = season.length + 1;
  const { bands, curves, years } = cumulativeRainBand(c.clim, (y) => seasonForYear(c.cal!, y), L);
  const cumR = cumulative(obs, "precip", season.plant, L);
  const wb = p ? waterBalance(obs, season, p, asOf) : null;
  let k = -1;
  cumR.forEach((v, i) => { if (v != null && season.plant + i <= asOf) k = i; });
  const percentile = k >= 0 && curves.length >= 10 ? percentileRank(curves.map((cv) => cv[k]), cumR[k]!) : null;
  const normal = k >= 0 ? bands[k]?.p50 : undefined;
  const pctOfNormal = normal && normal > 0 ? (100 * cumR[k]!) / normal : null;
  const total = k >= 0 ? cumR[k]! : null;

  const lede = el("div", { class: "lede" });
  if (total != null) lede.append(el("div", {}, el("span", { class: "lede-v" }, fmt.mm(total)), el("span", { class: "lede-l" }, normal ? `normal ${fmt.mm(normal)}` : "")));
  if (wb && wb.totals.days > 0) lede.append(el("div", {}, el("span", { class: "lede-v" }, fmt.mm(wb.totals.gap)), el("span", { class: "lede-l" }, "short of crop need")));
  s.body.append(lede);

  const T = theme();
  const bandPts = bands.map((bd: Band, i) => ({ day: season.plant + i, lo: bd.p10, mid: bd.p50, hi: bd.p90 }));
  const lines: Line[] = [];
  if (wb) lines.push({ label: `${cropLabel} water need`, color: T.need, points: wb.cumEtc.map((y, i) => ({ day: season.plant + i, y })), width: 1.5 });
  if (cmp) lines.push({ label: `${cmp.season.year} season`, color: T.cmp, points: cumulative(cmp.data, "precip", cmp.season.plant, L).map((y, i) => ({ day: season.plant + i, y })) });
  lines.push({ label: "Rain this season", color: T.rain, points: cumR.map((y, i) => ({ day: season.plant + i, y: season.plant + i <= asOf ? y : null })) });
  s.body.append(keys([
    { label: "Rain this season", color: T.rain, kind: "line" },
    ...(wb ? [{ label: "Crop water need", color: T.need, kind: "line" as const }] : []),
    ...(cmp ? [{ label: `${cmp.season.year} season`, color: T.cmp, kind: "line" as const }] : []),
    { label: "Normal range", color: T.band, kind: "band" },
  ]));
  chart(s.body, (w) => timeChart({ width: w, height: 230, unit: "mm", band: bandPts, bandLabel: "Normal", lines }));
  s.body.append(more("Table", tableView(["Date", "Rain (mm)", "Need (mm)", "Normal (mm)"],
    bandPts.filter((_, i) => i % 7 === 0 || i === k).map((bp) => {
      const i = bp.day - season.plant;
      return [fromDay(bp.day), r1(cumR[i]), wb ? r1(wb.cumEtc[i] ?? null) : null, `${r1(bp.lo)}–${r1(bp.hi)}`];
    }))));
  if (wb && wb.totals.days > 0) {
    s.body.append(el("div", { style: "margin-top:12px" }, el("div", { class: "m-label", style: "margin-bottom:6px" }, "Effective rain vs crop need so far (mm)"), chartless(needBars(wb.totals.effRain, wb.totals.etc, 380))));
  }
  s.about(
    `Accumulated rain from sowing (${fmtDay(season.plant)}) compared with the same days in 1991–2020 (shaded: 10th–90th percentile of ${years.length} seasons).${percentile != null ? ` This season is at the ${fmt.ord(percentile)} percentile.` : ""}`,
    wb ? `Crop water need is FAO-56 ETc = Kc × ET₀ for a healthy crop. Effective rain uses the USDA-SCS method (FAO CROPWAT). The shortfall is the need not covered by effective rain, summed by month; it excludes paddy flooding, land preparation and field losses.` : `Crop water need is not computed for this crop (${p?.kc_range ?? "no FAO-56 parameters"}).`,
    el("p", { class: "caption" }, "ERA5 via Open-Meteo · FAO-56 Tables 11–12"));
  return { gap: wb ? wb.totals.gap : null, percentile, pctOfNormal, total };
}

function chartless(n: Node): HTMLElement {
  const d = el("div", { class: "chart" });
  d.append(n);
  return d;
}

// =====================================================================
function renderTemp(s: Sec, c: RenderCtx, obs: Daily, range: [Day, Day], p: CropParams | null,
  season: Season | null, cmp: { season: Season; data: Daily } | null, cropLabel: string) {
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
  const lede = el("div", { class: "lede" });
  if (avg != null) lede.append(el("div", {}, el("span", { class: "lede-v" }, fmt.c(avg)), el("span", { class: "lede-l" }, "average maximum")));
  if (hot != null) lede.append(el("div", {}, el("span", { class: "lede-v" }, `${hot}`), el("span", { class: "lede-l" }, `days above ${thr} °C${normal != null ? ` (normal ${Math.round(normal)})` : ""}`)));
  s.body.append(lede);
  const lines: Line[] = [];
  if (cmp && season) {
    const ix = indexOf(cmp.data);
    lines.push({ label: `${cmp.season.year} season`, color: T.cmp, points: pts.map((pt) => {
      const i = ix.get(cmp.season.plant + (pt.day - season.plant));
      return { day: pt.day, y: i === undefined ? null : cmp.data.tmax[i] };
    }), width: 1.5 });
  }
  lines.push({ label: "Daily maximum", color: T.rain, points: pts, width: 1.5 });
  s.body.append(keys([
    { label: "Daily maximum", color: T.rain, kind: "line" },
    ...(cmp ? [{ label: `${cmp.season.year} season`, color: T.cmp, kind: "line" as const }] : []),
    { label: "Normal range", color: T.band, kind: "band" },
  ]));
  chart(s.body, (w) => timeChart({ width: w, height: 200, unit: "°C", band: bandOnDates(bands, range[0], range[1]), lines, hline: thr != null ? { y: thr, label: `${thr} °C` } : undefined }));
  s.body.append(more("Table", tableView(["Date", "Max (°C)", "Min (°C)"], pts.map((pt, i) => [fromDay(pt.day), r1(pt.y), r1(seriesOn(obs, "tmin", range[0], range[1])[i]?.y ?? null)]))));
  s.about(
    `Daily maximum temperature against the 1991–2020 normal range for each date (10th–90th percentile).`,
    thr != null ? `${thr} °C is the level above which ${cropLabel.toLowerCase()} yields are reported to fall: ${p?.heat_ref ? c.params.references[p.heat_ref] : ""}` : "",
    el("p", { class: "caption" }, "ERA5 via Open-Meteo"));
  return { hot, normal, avg };
}

// =====================================================================
function renderSoilAir(s: Sec, c: RenderCtx, obs: Daily, range: [Day, Day], asOf: Day) {
  const T = theme();
  const at = asOf;
  const ix = indexOf(obs);
  const vars: { v: "sm" | "rh" | "et0"; label: string; unit: string; scale: number; lo: string; hi: string; dp: number }[] = [
    { v: "sm", label: "Soil moisture, top 1 m", unit: "% vol", scale: 100, lo: "Dry", hi: "Wet", dp: 0 },
    { v: "rh", label: "Relative humidity", unit: "%", scale: 1, lo: "Dry", hi: "Humid", dp: 0 },
    { v: "et0", label: "Evaporation demand (ET₀)", unit: "mm/day", scale: 1, lo: "Low", hi: "High", dp: 1 },
  ];
  let smOut: { pct: number | null; value: number | null } = { pct: null, value: null };
  const wrap = el("div", {});
  s.body.append(wrap);
  const from = Math.max(range[0], at - 89);
  for (const x of vars) {
    const i = ix.get(at);
    const raw = i === undefined ? null : obs[x.v][i];
    const pct = raw != null ? doyPercentile(c.clim, x.v, at, raw) : null;
    if (x.v === "sm") smOut = { pct, value: raw };
    const row = el("div", { class: "var" });
    const left = el("div", {}, el("div", { class: "var-l" }, x.label),
      el("div", { class: "var-v" }, raw != null ? `${(raw * x.scale).toFixed(x.dp)} ` : "–", raw != null ? el("span", { class: "m-unit" }, x.unit) : null));
    if (pct != null) left.append(el("div", { class: "var-p" }, pctBar(pct, 200, x.lo, x.hi)));
    row.append(left);
    const pts = seriesOn(obs, x.v, from, at, x.scale);
    if (finite(pts.map((q) => q.y)).length) {
      const bands = doyBands(c.clim, x.v).map((bd) => bd && ({ p10: bd.p10 * x.scale, p50: bd.p50 * x.scale, p90: bd.p90 * x.scale }));
      const sp = el("div", {});
      row.append(sp);
      wrap.append(row);
      chart(sp, (w) => sparkline(w, pts, bandOnDates(bands, from, at), T.rain), "chart");
    } else { wrap.append(row); }
  }
  s.about(`Values on ${fmtDay(at)} with their percentile for the time of year (1991–2020), and the last 90 days against the normal range. Soil moisture is modelled water content of the top metre, not a field measurement. ET₀ is how much water the air can draw from a well-watered field.`,
    el("p", { class: "caption" }, "ERA5 via Open-Meteo"));
  return smOut;
}

// =====================================================================
function renderForecast(s: Sec, c: RenderCtx, days: EnsembleDay[], p: CropParams | null) {
  void c;
  const rows = days.map((d) => ({
    day: d.day,
    rain: quantile(d.members.precip, 0.5), rainHi: quantile(d.members.precip, 0.9),
    tmax: quantile(d.members.tmax, 0.5), tmin: quantile(d.members.tmin, 0.5),
  }));
  const total = rows.reduce((a, r) => a + r.rain, 0);
  const thr = p?.heat_c ?? null;
  const hot = thr != null ? rows.filter((r) => r.tmax > thr).length : 0;
  s.body.append(el("div", { class: "lede" },
    el("div", {}, el("span", { class: "lede-v" }, fmt.mm(total)), el("span", { class: "lede-l" }, `rain, ${rows.filter((r) => r.rain >= 0.5).length} wet days`)),
    thr != null ? el("div", {}, el("span", { class: "lede-v" }, `${hot}`), el("span", { class: "lede-l" }, `days above ${thr} °C`)) : null));
  s.body.append(forecastList(rows, thr));
  s.body.append(more("Table", tableView(["Date", "Rain (mm)", "Rain, wet case (mm)", "Min (°C)", "Max (°C)"],
    rows.map((r) => [fromDay(r.day), r1(r.rain), r1(r.rainHi), r1(r.tmin), r1(r.tmax)]))));
  s.about("Median of the ECMWF ensemble for each day. Rain in mm; the bar length shows the amount. The coloured bar spans the day's minimum to maximum temperature; the thin orange line marks the crop's heat threshold. The table adds a wet case (90th percentile of the ensemble).",
    el("p", { class: "caption" }, `ECMWF IFS 0.25° ensemble, ${days[0]?.members.precip.length ?? 0} members, via Open-Meteo`));
}

function renderOutlook(s: Sec, months: SeasonalMonth[], target: Season | null, tp: StagePlan | null) {
  let m0: Day | null = null;
  let m1: Day | null = null;
  if (target && tp) { m0 = target.plant + tp.bounds[1]; m1 = target.plant + tp.bounds[2] - 1; }
  const items = months.map((m) => {
    const start = toDay(m.month + "-01");
    return { label: monthName(Number(m.month.slice(5, 7))), pct: m.precipPct, tAnom: m.tAnom, stage: m0 != null && m1 != null && start <= m1 && start + 30 >= m0 };
  });
  s.body.append(el("p", { class: "lede-l", style: "margin:0 0 10px" }, "Rain compared with normal, and temperature difference (°C)"));
  s.body.append(outlookStrip(items, m0 != null));
  s.body.append(more("Table", tableView(["Month", "Rain (mm)", "vs normal", "Temp vs normal"], months.map((m) => [
    m.month, m.precipMm != null ? Math.round(m.precipMm) : null,
    m.precipPct != null ? `${m.precipPct > 0 ? "+" : ""}${Math.round(m.precipPct)}%` : null,
    m.tAnom != null ? `${m.tAnom > 0 ? "+" : ""}${m.tAnom.toFixed(1)} °C` : null]))));
  s.about(`Monthly rain from the ECMWF seasonal forecast, compared with the model's own normal for that month.${m0 != null ? ` The black line marks months in the crop's flowering stage (${fmtDay(m0)} – ${fmtDay(m1!)}).` : ""} Seasonal forecasts give the tendency over a wide area and are often wrong at a single place.`,
    el("p", { class: "caption" }, "ECMWF SEAS5, 51-member ensemble mean, via Open-Meteo"));
}

// =====================================================================
function renderAfter(s: Sec, c: RenderCtx, obs: Daily, D: Day) {
  const T = theme();
  const last = lastEra5Day();
  const end16 = Math.min(D + 16, last);
  if (end16 <= D) { s.body.append(note("No observations after this date yet.")); return; }
  const r = recentRain(obs, c.clim, end16, end16 - D);
  s.body.append(el("div", { class: "lede" }, el("div", {}, el("span", { class: "lede-v" }, fmt.mm(r.total)), el("span", { class: "lede-l" }, `rain in the next ${end16 - D} days${r.normal != null ? ` (normal ${fmt.mm(r.normal)})` : ""}`))));
  s.body.append(keys([{ label: "Daily maximum", color: T.rain, kind: "line" }, { label: "Normal range", color: T.band, kind: "band" }]));
  chart(s.body, (w) => timeChart({ width: w, height: 180, unit: "°C", band: bandOnDates(doyBands(c.clim, "tmax"), D + 1, end16), lines: [{ label: "Daily maximum", color: T.rain, points: seriesOn(obs, "tmax", D + 1, end16), width: 1.5 }] }));
  const months = monthlyVsNormal(obs, c.clim, D + 1, Math.min(D + 214, last));
  if (months.length) {
    const s2 = section(s.el.parentElement!, "Following months");
    s2.body.append(el("p", { class: "lede-l", style: "margin:0 0 10px" }, "Rain compared with the 1991–2020 average"));
    s2.body.append(outlookStrip(months.map((m) => ({ label: monthName(m.m), pct: m.normal >= 10 ? m.pct : null, tAnom: null, stage: false })), false));
    s2.body.append(more("Table", tableView(["Month", "Rain (mm)", "Normal (mm)", "Departure"], months.map((m) => [`${m.y}-${String(m.m).padStart(2, "0")}`, Math.round(m.rain), Math.round(m.normal), m.pct != null ? `${Math.round(m.pct)}%` : null]))));
  }
  s.about("What was observed after the selected date, compared with the 1991–2020 normal.", el("p", { class: "caption" }, "ERA5 via Open-Meteo"));
}

// =====================================================================
function ensoMetric(e: EnsoData | null, D: Day, current: boolean): HTMLElement | null {
  if (!e) return null;
  const { y, m } = ymd(D);
  const val = current ? e.latest.value : indexValue(e, y, m);
  if (val == null) return null;
  const phase = val >= 0.5 ? "El Niño" : val <= -0.5 ? "La Niña" : "Neutral";
  const run = current ? e.run_in_progress : null;
  return metric({
    label: "Pacific (ENSO)", value: `${val > 0 ? "+" : ""}${val.toFixed(1)}`, unit: "°C",
    ctx: run ? `${run.seasons_so_far} season${run.seasons_so_far > 1 ? "s" : ""} at ${run.type === "El Nino" ? "El Niño" : "La Niña"} level` : current ? `${e.index}, ${monthName(Number(e.latest.month.slice(5)))}` : `${monthName(m)} ${y}`,
    status: statusTag(phase === "Neutral" ? "good" : Math.abs(val) >= 1.5 ? "bad" : "warn", phase === "Neutral" ? "Neutral" : `${phase}${Math.abs(val) >= 1.5 ? ", strong" : ""}`),
  });
}

function renderEnso(tab: HTMLElement, c: RenderCtx, D: Day, current: boolean, season: Season | null, loadHistory: () => Promise<History>, auto: boolean) {
  const e = c.enso;
  const s = section(tab, "El Niño and La Niña");
  if (!e) { s.body.append(note("ENSO data not available.", "note error")); return; }
  const T = theme();
  const [y0, m0] = e.start.split("-").map(Number);
  const series = e.values.map((v, i) => ({ date: new Date(Date.UTC(y0, m0 - 1 + i, 15)), v })).filter((x): x is { date: Date; v: number } => x.v != null);
  const { y, m } = ymd(D);
  const val = current ? e.latest.value : indexValue(e, y, m);
  const phase = val == null ? "" : val >= 0.5 ? "El Niño" : val <= -0.5 ? "La Niña" : "Neutral";
  s.body.append(el("div", { class: "lede" }, el("div", {},
    el("span", { class: "lede-v" }, val != null ? `${val > 0 ? "+" : ""}${val.toFixed(2)} °C` : "–"),
    el("span", { class: `phase ${phase === "El Niño" ? "nino" : phase === "La Niña" ? "nina" : ""}` }, phase),
    el("span", { class: "lede-l" }, `${e.index}, ${current ? e.latest.month : `${y}-${String(m).padStart(2, "0")}`}`))));
  s.body.append(keys([{ label: "El Niño", color: T.nino, kind: "band" }, { label: "La Niña", color: T.nina, kind: "band" }]));
  chart(s.body, (w) => ensoArea(w, series, current ? undefined : toDate(D)));
  s.about(
    `${e.index === "RONI" ? "The Relative Oceanic Niño Index (RONI)" : "The Oceanic Niño Index (ONI)"} tracks how warm the central Pacific is. El Niño: +0.5 °C or more for five overlapping 3-month seasons in a row; La Niña: −0.5 °C or less. Shaded areas are the values beyond those limits.`,
    el("p", {}, "Official outlooks: ", el("a", { href: "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml" }, "NOAA CPC"), " · ", el("a", { href: "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/" }, "IRI")),
    el("p", { class: "caption" }, `NOAA CPC ${e.index}, updated ${e.generated_utc}`));

  if (current && e.seas5_nino34?.months?.length) {
    const s5 = e.seas5_nino34;
    const f = section(tab, "Pacific outlook");
    f.body.append(el("p", { class: "lede-l", style: "margin:0 0 4px" }, "Niño-3.4 sea-surface temperature anomaly forecast (°C)"));
    chart(f.body, (w) => monthBars(w, s5.months.map((mo, i) => ({ label: monthName(Number(mo.slice(5))), v: s5.anomaly_c[i] }))));
    f.about(s5.description, el("p", { class: "caption" }, "ECMWF SEAS5 via Open-Meteo"));
  }

  // Local history
  const h = section(tab, "Past El Niño seasons here");
  const what = historyWhat(c, historyCal(c, D), D);
  const btn = el("button", { class: "cta", type: "button" }, "Compare 75 years of seasons");
  h.body.append(el("p", { class: "lede-l", style: "margin:0 0 8px" }, `Rain and heat in each ${what}, 1950 to today`), btn);
  h.about("Uses NOAA's official El Niño and La Niña episodes. A season counts as El Niño or La Niña when more than half of it falls in an episode. Past seasons are not a forecast: every El Niño is different.", el("p", { class: "caption" }, "ERA5 via Open-Meteo · NOAA CPC"));
  const run = async () => {
    btn.disabled = true;
    btn.textContent = "Loading 75 seasons…";
    try {
      const hist = await loadHistory();
      if (!c.alive()) return;
      btn.remove();
      if (!hist.comp) { h.body.append(note("Not enough complete seasons to compare.")); return; }
      renderComposite(h, hist.comp, season ? [season.year, ...(c.state.cmp ? [c.state.cmp] : [])] : []);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Retry";
      c.setStatus(`El Niño history failed: ${(err as Error).message}`, true);
    }
  };
  btn.addEventListener("click", run);
  if (auto) void run();
}

const pFmt = (p: number) => (p < 0.001 ? "<0.001" : p.toFixed(2));

function renderComposite(s: Sec, comp: Composite, highlight: number[]) {
  const T = theme();
  const n = comp.byPhase["El Nino"];
  const neu = comp.byPhase["Neutral"];
  const sig = comp.pRainNinoVsNeutral < 0.05;
  s.body.replaceChildren();
  if (n.n > 0) {
    s.body.append(el("div", { class: "lede" },
      el("div", {}, el("span", { class: "lede-v" }, `${n.drierCount} of ${n.n}`), el("span", { class: "lede-l" }, "El Niño seasons had below-normal rain")),
      el("div", {}, el("span", { class: "lede-v" }, fmt.pct(n.medianRainPct)), el("span", { class: "lede-l" }, `median (neutral ${fmt.pct(neu.medianRainPct)})`))));
    s.body.append(el("p", { class: "sig" }, sig ? `A consistent difference from neutral seasons (p = ${pFmt(comp.pRainNinoVsNeutral)}).` : `Not a consistent difference from neutral seasons (p = ${pFmt(comp.pRainNinoVsNeutral)}).`));
  }
  s.body.append(keys([{ label: "El Niño", color: T.nino, kind: "dot" }, { label: "Neutral", color: T.neutral, kind: "dot" }, { label: "La Niña", color: T.nina, kind: "dot" }, { label: "Median", color: T.ink, kind: "line" }]));
  s.body.append(el("div", { class: "m-label", style: "margin-top:8px" }, "Season rain vs 1991–2020 normal"));
  chart(s.body, (w) => beeswarm(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.rainPct })), "%", highlight));
  s.body.append(el("div", { class: "m-label", style: "margin-top:14px" }, "Season heat vs long-term trend"));
  chart(s.body, (w) => beeswarm(w, comp.points.map((p) => ({ year: p.year, phase: p.phase, v: p.tempAnom })), "°C", highlight));
  s.body.append(more("Table", tableView(["Season", "Phase", "Rain (mm)", "vs normal", "Heat vs trend (°C)"],
    [...comp.points].reverse().map((p) => [String(p.year), p.phase === "El Nino" ? "El Niño" : p.phase === "La Nina" ? "La Niña" : "Neutral", Math.round(p.rain), `${Math.round(p.rainPct)}%`, r1(p.tempAnom)]))));
  s.about(`Seasons ${comp.firstYear}–${comp.lastYear}. Rain is the season total as a percentage difference from the 1991–2020 average (${Math.round(comp.normalRain)} mm). Heat is the season's mean daily maximum temperature after removing the long-term warming trend: El Niño median ${fmt.dc(n.medianTempAnom)} vs neutral ${fmt.dc(neu.medianTempAnom)} (p = ${pFmt(comp.pTempNinoVsNeutral)}). p-values come from a rank-based permutation test; below 0.05 means the difference is unlikely to be chance. Outlined dots are the seasons you selected.`);
}

// =====================================================================
function renderAdvice(b: HTMLElement, items: Advice[]) {
  if (!items.length) { b.append(el("div", { class: "recs-ok" }, "Nothing unusual right now. Continue normal practice.")); return; }
  for (const a of items) {
    const why = el("div", { class: "rec-why", hidden: "" }, el("p", {}, a.trigger), el("p", {}, `Source: ${a.source}`));
    const btn = el("button", { class: "linkbtn", type: "button", "aria-expanded": "false" }, "Why?");
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      why.hidden = open;
      btn.textContent = open ? "Why?" : "Hide";
    });
    b.append(el("div", { class: "rec" }, el("div", { class: "rec-t" }, a.title), el("div", { class: "rec-a" }, a.action), btn, why));
  }
}
