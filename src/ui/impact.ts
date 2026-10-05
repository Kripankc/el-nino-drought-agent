// Left-panel blocks that appear on their own when the selected date falls in an
// El Niño or La Niña period: how past seasons of that phase went here, how this
// season compares, and the coming weeks and months.
import { Day, fmtDay, monthName, toDay, ymd } from "../lib/dates";
import { Band, Daily, cumulative, cumulativeRainBand, indexOf } from "../calc/climate";
import { EnsoData, EnsoState, PhaseImpact, tendency } from "../calc/enso";
import { Season } from "../calc/season";
import { finite, mean, median, percentileRank } from "../calc/stats";
import type { EnsembleDay, SeasonalMonth } from "../api/openmeteo";
import { chart, el, fmt, more, section } from "./dom";
import { keys, tableView, theme, timeChart } from "./charts";
import { compareStrip, divergingColor, pctStatus, statusTag, vsNormalBars } from "./visuals";

export const phaseName = (p: string) => (p === "El Nino" ? "El Niño" : p === "La Nina" ? "La Niña" : "Neutral");
const pFmt = (p: number) => (p < 0.001 ? "<0.001" : p.toFixed(2));
const signed = (x: number, dp = 0) => `${x > 0 ? "+" : ""}${x.toFixed(dp)}`;

/** One line on the state of the Pacific for the selected date. */
export function stateLine(e: EnsoData, st: EnsoState, D: Day, current: boolean): string {
  const name = phaseName(st.phase);
  if (!current) {
    const ep = e.episodes.find((x) => x.type === st.phase && toDay(x.start + "-01") <= D && D <= toDay(x.end + "-28") + 3);
    return ep ? `${name} episode ${monthLabel(ep.start)} – ${monthLabel(ep.end)}, peak ${signed(ep.peak, 1)} °C (NOAA CPC ${e.index})` : `${name} episode (NOAA CPC ${e.index})`;
  }
  const parts: string[] = [];
  if (st.value != null) parts.push(`${e.index} ${signed(st.value, 1)} °C in ${monthLabel(e.latest.month)}`);
  if (e.run_in_progress) parts.push(`${e.run_in_progress.seasons_so_far} of 5 seasons needed for an official episode`);
  const through = persistsThrough(e, st.phase);
  if (through) parts.push(`ECMWF model keeps ${name} conditions through ${through}`);
  return parts.join(" · ");
}

function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${monthName(m)} ${y}`;
}

/** Last month of the SEAS5 Niño-3.4 forecast in an unbroken run beyond ±0.5 °C, from the first month. */
function persistsThrough(e: EnsoData, phase: string): string | null {
  const s = e.seas5_nino34;
  if (!s?.months?.length) return null;
  let last: string | null = null;
  for (let i = 0; i < s.months.length; i++) {
    const v = s.anomaly_c[i];
    if (v == null || (phase === "El Nino" ? v < 0.5 : v > -0.5)) break;
    last = s.months[i];
  }
  return last ? monthLabel(last) : null;
}

export function impactSkeleton(box: HTMLElement, st: EnsoState, current: boolean) {
  box.replaceChildren();
  const name = phaseName(st.phase);
  const s = section(box, current ? `${name} impact here` : `${name} at this time`);
  s.body.append(el("p", { class: "lede-l", style: "margin:0 0 10px" }, `Comparing this place's rain in every ${name} season since 1950…`),
    el("div", { class: "sk", style: "height:120px" }));
  return s;
}

export interface ImpactView {
  enso: EnsoData;
  state: EnsoState;
  impact: PhaseImpact;
  all: Daily;                      // per-season ERA5 rain/Tmax, 1950 to the last complete season
  seasonFor: (y: number) => Season;
  focus: Season;                   // season being looked at (current/next, or the past one)
  obs: Daily;
  obsUntil: Day;                   // last observed day to show
  D: Day;
  current: boolean;
  inSeason: boolean;
  what: string;                    // "maize season, 15 Jun – 10 Oct" or "six months from Oct"
}

export function renderImpact(box: HTMLElement, v: ImpactView) {
  box.replaceChildren();
  const T = theme();
  const x = v.impact;
  const name = phaseName(x.phase);
  const color = x.phase === "El Nino" ? T.nino : T.nina;
  const s = section(box, v.current ? `${name} impact here` : `${name} at this time`);
  s.el.classList.add("impact", x.phase === "El Nino" ? "nino" : "nina");
  const badge = { active: v.current ? "Under way" : "Episode", developing: "Developing", expected: "Forecast" }[v.state.status];
  s.body.append(el("div", { class: "ix-state" }, el("span", { class: `phase ${x.phase === "El Nino" ? "nino" : "nina"}` }, `${name} · ${badge}`),
    el("span", {}, stateLine(v.enso, v.state, v.D, v.current))));

  // ---- curves: normal band, typical phase season, last phase season, this season
  const L = x.curve.length;
  const { bands, curves } = cumulativeRainBand(v.all, v.seasonFor, L);
  const plant = v.focus.plant;
  const until = Math.min(v.obsUntil, v.focus.harvest);
  const mine = until >= plant ? cumulative(v.obs, "precip", plant, L).map((y, k) => (plant + k <= until ? y : null)) : null;
  let k = -1;
  mine?.forEach((y, i) => { if (y != null) k = i; });

  // ---- headline numbers
  const t = tendency(x);
  const tiles = el("div", { class: "ix-tiles" });
  const tile = (label: string, value: string, ctx: string, viz?: Node | null, cls = "") =>
    tiles.append(el("div", { class: `ix-tile ${cls}` }, el("div", { class: "m-label" }, label), el("div", { class: "ix-v" }, value), el("div", { class: "m-ctx" }, ctx), viz ?? null));
  tile(`Typical ${name} season`, fmt.pct(x.medianRainPct), `rain vs normal · ${x.drier} of ${x.n} drier`, seasonDots(x));
  if (x.strong && (v.state.value == null || Math.abs(v.state.value) >= 1.5 || v.state.status === "expected")) {
    tile(`Strong ${name} seasons`, fmt.pct(x.strong.medianRainPct), `${x.strong.drier} of ${x.strong.n} drier · ${x.strong.years.join(", ")}`);
  }
  if (x.last) tile(`Last ${name} season`, fmt.pct(x.last.rainPct), `${seasonLabel(v.seasonFor(x.last.year))}${x.last.peak != null ? ` · peak ${signed(x.last.peak, 1)} °C` : ""}`);
  if (k >= 0 && bands[k]?.p50 > 0) {
    const pct = (100 * (mine![k]! - bands[k].p50)) / bands[k].p50;
    const typ = x.curve[k];
    const typPct = typ != null ? (100 * (typ - bands[k].p50)) / bands[k].p50 : null;
    const pr = curves.length >= 10 ? percentileRank(curves.map((cv) => cv[k]), mine![k]!) : null;
    const stt = pr != null ? pctStatus(pr) : null;
    tile(v.current ? "This season so far" : "This season", fmt.pct(pct),
      `${fmt.mm(mine![k]!)} by ${fmtDay(plant + k)}${typPct != null ? ` · typical ${name} ${fmt.pct(typPct)}` : ""}`,
      stt ? statusTag(stt.s, stt.word) : null, "now");
  } else if (v.current && plant > v.obsUntil) {
    tile("Next season", `${plant - v.obsUntil} days`, `until sowing on ${fmtDay(plant)}`, null, "now");
  }
  s.body.append(tiles);
  s.body.append(el("p", { class: "sig" }, t === "dry"
    ? `${name} seasons here have tended to be drier than normal${x.pRain < 0.05 ? ` and clearly differ from neutral seasons (p = ${pFmt(x.pRain)})` : `, but the difference from neutral seasons is not statistically clear (p = ${pFmt(x.pRain)})`}.`
    : t === "wet"
      ? `${name} seasons here have tended to be wetter than normal${x.pRain < 0.05 ? ` and clearly differ from neutral seasons (p = ${pFmt(x.pRain)})` : `, but the difference from neutral seasons is not statistically clear (p = ${pFmt(x.pRain)})`}.`
      : `No consistent ${name} effect on rain for this season here (p = ${pFmt(x.pRain)}): past ${name} seasons were both drier and wetter.`));

  // ---- chart
  const bandPts = bands.map((bd: Band, i) => ({ day: plant + i, lo: bd.p10, mid: bd.p50, hi: bd.p90 }));
  const lines: { label: string; color: string; points: { day: Day; y: number | null }[]; width?: number; dash?: string }[] = [
    { label: `Typical ${name} (median)`, color, points: x.curve.map((y, i) => ({ day: plant + i, y })), width: 2.2 },
  ];
  if (x.lastCurve) lines.push({ label: `${x.last!.year} (last ${name})`, color, points: x.lastCurve.map((y, i) => ({ day: plant + i, y })), width: 1.4, dash: "4 3" });
  if (mine && k >= 0) lines.push({ label: v.current ? "This season" : `${v.focus.year} season`, color: T.ink, points: mine.map((y, i) => ({ day: plant + i, y })), width: 2.2 });
  s.body.append(el("div", { class: "m-label", style: "margin:14px 0 2px" }, `Rain since sowing, ${seasonLabel(v.focus)}`));
  s.body.append(keys([
    ...(mine && k >= 0 ? [{ label: v.current ? "This season" : `${v.focus.year}`, color: T.ink, kind: "line" as const }] : []),
    { label: `Typical ${name}`, color, kind: "line" },
    ...(x.last ? [{ label: `${x.last.year}`, color, kind: "dot" as const }] : []),
    { label: "Normal range", color: T.band, kind: "band" },
  ]));
  chart(s.body, (w) => timeChart({ width: w, height: 210, unit: "mm", band: bandPts, bandLabel: "Normal 1991–2020", lines, vline: !v.current && v.D >= plant && v.D <= v.focus.harvest ? { day: v.D, label: "Selected" } : undefined }));

  // ---- month by month
  const ix = indexOf(v.obs);
  const obsPct = x.months.map((mo) => {
    if (plant + mo.to > until || mo.normal < 10) return null;
    let acc = 0;
    for (let d = plant + mo.from; d <= plant + mo.to; d++) { const p = v.obs.precip[ix.get(d) ?? -1]; if (p == null) return null; acc += p; }
    return (100 * (acc - mo.normal)) / mo.normal;
  });
  const rows = [{ label: `Typical ${name}`, values: x.months.map((m) => m.medianPct) }];
  if (obsPct.some((p) => p != null)) rows.push({ label: v.current ? "This season" : `${v.focus.year}`, values: obsPct });
  s.body.append(el("div", { class: "m-label", style: "margin:16px 0 8px" }, "Month by month, rain vs normal"));
  s.body.append(compareStrip(x.months.map((m) => monthName(m.m)), rows));

  // ---- heat
  const hot = x.pTemp < 0.05;
  s.body.append(el("p", { class: "sig", style: "margin-top:12px" },
    `Heat: ${name} seasons here were ${Math.abs(x.medianTempAnom) < 0.05 ? "about as warm as" : `a median ${Math.abs(x.medianTempAnom).toFixed(1)} °C ${x.medianTempAnom > 0 ? "warmer" : "cooler"} than`} the long-term trend (daily maximum)${hot ? `, a clear difference (p = ${pFmt(x.pTemp)})` : `; not a clear difference (p = ${pFmt(x.pTemp)})`}.`));

  s.body.append(more("Table", tableView(["Month", "Normal (mm)", `Typical ${name}`, rows[1]?.label ?? "This season"],
    x.months.map((m, i) => [monthName(m.m), Math.round(m.normal), m.medianPct != null ? fmt.pct(m.medianPct) : null, obsPct[i] != null ? fmt.pct(obsPct[i]!) : null]))));
  s.about(
    `Each year's ${v.what} from 1950 to the last complete season, from ERA5. A season counts as ${name} when more than half of its days fall in an official NOAA CPC ${name} episode (${x.years.length} seasons: ${x.years.join(", ")}).`,
    `“Typical” is the median of those seasons. Rain is compared with the 1991–2020 average for the same days. The p-value compares ${name} seasons with neutral seasons using a rank-based permutation test; below 0.05 means the difference is unlikely to be chance. Strong events are those whose episode peaked at ±1.5 °C or more.`,
    `Past ${name} seasons are not a forecast: each event is different, and other influences (such as the Indian Ocean) also matter. ${v.current ? "The current event is not yet counted among past seasons." : `The ${v.focus.year} season is left out of the typical values so it is not compared with itself.`}`,
    el("p", { class: "caption" }, `ERA5 via Open-Meteo · NOAA CPC ${v.enso.index} episodes`));
}

function seasonLabel(s: Season): string {
  const a = ymd(s.plant);
  const b = ymd(s.harvest);
  return `${monthName(a.m)} ${a.y} – ${monthName(b.m)} ${b.y}`;
}

/** One small square per phase season, coloured by its rain departure. */
function seasonDots(x: PhaseImpact): HTMLElement {
  const wrap = el("div", { class: "ix-dots", role: "img", "aria-label": `${x.n} past seasons: ${x.drier} drier, ${x.wetter} wetter than normal` });
  x.years.forEach((y, i) => {
    const c = divergingColor(Math.max(-60, Math.min(60, x.rainPcts[i])));
    const d = el("i", { title: `${y}: ${fmt.pct(x.rainPcts[i])}` });
    d.style.background = c.bg;
    wrap.append(d);
  });
  return wrap;
}

// =====================================================================
export interface ComingView {
  fc: EnsembleDay[] | null;
  fc15: { total: number; normal: number; percentile: number; hot: number | null; hotNormal: number | null } | null;
  heatC: number | null;
  seasonal: SeasonalMonth[] | null;
  impact: PhaseImpact | null;
  state: EnsoState | null;
  enso: EnsoData | null;
}

export function renderComing(box: HTMLElement, v: ComingView) {
  box.replaceChildren();
  if (!v.fc && !v.seasonal) return;
  const T = theme();
  const s = section(box, "Coming weeks and months");
  const tiles = el("div", { class: "ix-tiles" });
  if (v.fc15) {
    // Where these dates are normally (almost) dry, a percentile says little
    const dryTime = v.fc15.normal < 5;
    const st = pctStatus(v.fc15.percentile);
    tiles.append(el("div", { class: "ix-tile" }, el("div", { class: "m-label" }, "Rain, next 15 days"),
      el("div", { class: "ix-v" }, fmt.mm(v.fc15.total)), el("div", { class: "m-ctx" }, dryTime ? "usually dry on these dates" : `normal ${fmt.mm(v.fc15.normal)} for these dates`),
      el("div", { class: "m-viz" }, vsNormalBars(v.fc15.total, v.fc15.normal, 220, ["forecast", "normal"], T.rain)), dryTime ? null : statusTag(st.s, st.word)));
    if (v.heatC != null && v.fc15.hot != null) {
      const more_ = v.fc15.hotNormal != null && v.fc15.hot > v.fc15.hotNormal;
      tiles.append(el("div", { class: "ix-tile" }, el("div", { class: "m-label" }, `Days above ${v.heatC} °C`),
        el("div", { class: "ix-v" }, `${v.fc15.hot}`), el("div", { class: "m-ctx" }, v.fc15.hotNormal != null ? `normal ${Math.round(v.fc15.hotNormal)} for these dates` : "next 15 days"),
        v.fc15.hotNormal != null ? statusTag(more_ ? (v.fc15.hot >= v.fc15.hotNormal + 3 ? "bad" : "warn") : "good", more_ ? "More than normal" : "Normal or fewer") : null));
    }
  }
  if (tiles.childElementCount) s.body.append(tiles);

  if (v.seasonal?.length) {
    const ms = v.seasonal.slice(0, 6);
    const rows: { label: string; values: (number | null)[] }[] = [{ label: "Forecast", values: ms.map((m) => m.precipPct) }];
    if (v.impact) {
      rows.push({ label: `Past ${phaseName(v.impact.phase)}`, values: ms.map((m) => v.impact!.months.find((x) => x.m === Number(m.month.slice(5, 7)))?.medianPct ?? null) });
    }
    s.body.append(el("div", { class: "m-label", style: "margin:16px 0 8px" }, "Rain vs normal, next months"));
    s.body.append(compareStrip(ms.map((m) => monthName(Number(m.month.slice(5, 7)))), rows));
    const tA = finite(ms.slice(0, 3).map((m) => m.tAnom));
    if (tA.length) {
      const a = mean(tA);
      s.body.append(el("p", { class: "sig", style: "margin-top:10px" }, `Temperature over the next three months: ${signed(a, 1)} °C ${Math.abs(a) < 0.25 ? "(near normal)" : a > 0 ? "warmer than normal" : "cooler than normal"}.`));
    }
    if (v.state && v.enso) {
      const through = persistsThrough(v.enso, v.state.phase);
      if (through) s.body.append(el("p", { class: "sig" }, `Pacific: the ECMWF model keeps ${phaseName(v.state.phase)} conditions through ${through}.`));
    }
  }
  s.about(
    v.fc15 ? `Next 15 days: median of the ECMWF ensemble, compared with ERA5 rain on the same dates in 1991–2020. The forecast model and ERA5 are different models, so treat small differences with care.` : "",
    v.seasonal ? `Next months: ECMWF SEAS5 ensemble mean against the model's own normal for each month.${v.impact ? ` The second row is the median of past ${phaseName(v.impact.phase)} seasons here, for the months inside the crop season.` : ""} Seasonal forecasts show the tendency over a wide area and are often wrong at a single place.` : "",
    el("p", { class: "caption" }, "ECMWF IFS ensemble and SEAS5 via Open-Meteo · ERA5"));
}

/** Next-15-day ensemble median vs the same dates in 1991-2020. */
export function forecastVsNormal(fc: EnsembleDay[], normal: { rain: number[]; hot: number[] }, heatC: number | null): ComingView["fc15"] {
  if (!fc.length || normal.rain.length < 10) return null;
  const total = fc.reduce((a, d) => a + median(d.members.precip), 0);
  const hot = heatC != null ? fc.filter((d) => median(d.members.tmax) > heatC).length : null;
  return { total, normal: median(normal.rain), percentile: percentileRank(normal.rain, total), hot, hotNormal: heatC != null ? median(normal.hot) : null };
}

