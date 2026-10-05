// "When to sow" tab: rainy-season onset at this place for the selected crop.
import { Day, fmtDay, fromDay, ymd } from "../lib/dates";
import { CLIM_END, CLIM_START, Daily } from "../calc/climate";
import { Season } from "../calc/season";
import { Composite } from "../calc/enso";
import { OnsetSummary, OnsetYear, WINDOW_AFTER, WINDOW_BEFORE, medianShift, onsetSoFar, onsetYears, summarise } from "../calc/onset";
import { el, more, note, section, chart } from "./dom";
import { keys, tableView, theme, timeChart } from "./charts";

const short = (d: Day) => fmtDay(d).replace(/ \d{4}$/, "");

export interface SowingNormals { years: OnsetYear[]; s: OnsetSummary; applies: "yes" | "wet" | "no" | "nodata" }

/** 1991-2020 onsets and whether the rule applies here. */
export function sowingNormals(clim: Daily, seasonFor: (y: number) => Season): SowingNormals {
  const years: number[] = [];
  for (let y = CLIM_START; y <= CLIM_END; y++) {
    const p = seasonFor(y).plant;
    if (ymd(p - WINDOW_BEFORE).y >= CLIM_START && ymd(p + WINDOW_AFTER + 33).y <= CLIM_END) years.push(y);
  }
  const ys = onsetYears(clim, seasonFor, years);
  const s = summarise(ys);
  const applies = s.n < 15 ? "nodata" : s.alwaysWet ? "wet" : s.found < 0.5 * s.n ? "no" : "yes";
  return { years: ys, s, applies };
}

/** Headline sentence, e.g. "Rains had properly started by 20 Jun in 8 of 10 years". */
export function sowingHeadline(n: SowingNormals, focus: Season): string | null {
  if (n.applies !== "yes") return null;
  if (n.s.p80 != null) return `Rains had properly started by ${short(focus.plant + n.s.p80)} in 8 of 10 years`;
  if (n.s.median != null) return `Rains usually start around ${short(focus.plant + n.s.median)}, but in more than 2 of 10 years after ${short(focus.plant + WINDOW_AFTER)}`;
  return null;
}

export interface SowingView {
  tab: HTMLElement;
  normals: SowingNormals;
  focus: Season;                    // season being planned (current or next)
  seasonFor: (y: number) => Season;
  obs: Daily;
  until: Day;                       // last observed day to use
  current: boolean;
  irrigated: boolean;
  cropLabel: string;
  loadHistory: () => Promise<{ all: Daily; comp: Composite | null }>;
  autoHistory: boolean;
  alive: () => boolean;
}

export function renderSowing(v: SowingView) {
  const T = theme();
  const s = section(v.tab, `When to sow ${v.cropLabel.toLowerCase()}`);
  s.about(
    "The rainy season counts as started on the first day with at least 20 mm of rain over 3 days that is not followed by a dry spell of 7 or more days (each under 1 mm) within the next 30 days (Sivakumar 1988, Agricultural and Forest Meteorology 42:295–305). A false start is heavy rain followed by such a dry spell: seed sown then often fails. The search runs from 60 days before to 60 days after the usual sowing date of this crop here (GGCMI crop calendar).",
    "Rain is ERA5 for a ~28 km cell, so local showers can differ. Before sowing, also check that the soil is moist to about a hand's depth. Local extension services may use other thresholds.",
    el("p", { class: "caption" }, "ERA5 via Open-Meteo · GGCMI Phase 3 crop calendar · NOAA CPC ENSO episodes"));
  const n = v.normals;
  if (n.applies === "nodata") { s.body.append(note("Not enough years of rain data around this crop's sowing time to estimate the start of the rains.")); return; }
  if (n.applies === "wet") { s.body.append(note(`Rain is usually plentiful throughout the sowing window here: in most years the 20 mm start condition is met at the very beginning. The start of the rains does not limit sowing ${v.cropLabel.toLowerCase()} here.`)); return; }
  if (n.applies === "no") {
    s.body.append(note(`In most years (${n.s.n - n.s.found} of ${n.s.n}) no reliable rainy-season start falls within two months of this crop's usual sowing date (${short(v.focus.plant)}). It is probably sown on stored soil moisture or with irrigation, so this rule does not apply here.`));
    return;
  }
  if (v.irrigated) s.body.append(el("p", { class: "sig", style: "margin:0 0 10px" }, "This is the irrigated calendar. Irrigated fields depend less on the rains; the dates below show when the rainy season usually starts."));

  // ---- headline tiles
  const sum = n.s;
  const tiles = el("div", { class: "ix-tiles" });
  const tile = (label: string, value: string, ctx: string) => tiles.append(el("div", { class: "ix-tile" }, el("div", { class: "m-label" }, label), el("div", { class: "ix-v" }, value), el("div", { class: "m-ctx" }, ctx)));
  tile("Safe to sow from", sum.p80 != null ? short(v.focus.plant + sum.p80) : "–", sum.p80 != null ? "rains had started by then in 8 of 10 years (1991–2020)" : "rains start later than the window in more than 2 of 10 years");
  tile("Usual start", sum.median != null ? short(v.focus.plant + sum.median) : "–", `middle year · usual sowing ${short(v.focus.plant)}`);
  tile("False starts", `${Math.round(sum.falseStartPct)}%`, "of years: first heavy rain followed by a week or more without rain");
  // this year
  const so = onsetSoFar(v.obs, v.focus.plant, v.until);
  const winStart = v.focus.plant - WINDOW_BEFORE;
  const thisYear = so.onset != null
    ? { v: short(v.focus.plant + so.onset), c: "the rains properly started (ERA5)" }
    : so.pending != null
      ? { v: `${short(v.focus.plant + so.pending)}?`, c: `heavy rain; it counts as the start if no week-long dry spell follows by ${short(so.pendingCheckEnd!)}` }
      : v.until < winStart
        ? { v: "–", c: `the sowing window opens ${short(winStart)}` }
        : { v: "Not yet", c: `no start found up to ${short(v.until)}` };
  tiles.append(el("div", { class: "ix-tile" }, el("div", { class: "m-label" }, v.current ? "This year" : `${ymd(v.focus.plant).y}`), el("div", { class: "ix-v" }, thisYear.v), el("div", { class: "m-ctx" }, thisYear.c)));
  s.body.append(tiles);

  // ---- chart: share of years started by each date
  const chartBox = el("div", {});
  s.body.append(el("div", { class: "m-label", style: "margin:16px 0 2px" }, "Share of years in which the rains had started, by date"), chartBox);
  const ensoBox = el("div", {});
  s.body.append(ensoBox);
  const draw = (nino: { pts: { day: number; pct: number }[]; n: number } | null) => {
    chartBox.replaceChildren();
    chartBox.append(keys([
      { label: "1991–2020", color: T.ink, kind: "line" },
      ...(nino ? [{ label: `El Niño years (${nino.n})`, color: T.nino, kind: "line" as const }] : []),
    ]));
    const lines = [{ label: "1991–2020", color: T.ink, width: 2, points: sum.byDay.map((p) => ({ day: v.focus.plant + p.day, y: Math.round(p.pct) })) }];
    if (nino) lines.push({ label: "El Niño years", color: T.nino, width: 2, points: nino.pts.map((p) => ({ day: v.focus.plant + p.day, y: Math.round(p.pct) })) });
    chart(chartBox, (w) => timeChart({ width: w, height: 200, unit: "% of years", lines, vline: { day: v.focus.plant, label: "usual sowing" } }));
  };
  draw(null);

  // ---- El Nino comparison
  const runHistory = () => {
    ensoBox.replaceChildren(el("p", { class: "lede-l" }, "Comparing with El Niño years since 1950…"));
    v.loadHistory().then((h) => {
      if (!v.alive()) return;
      ensoBox.replaceChildren();
      if (!h.comp) return;
      const ninoYears = h.comp.points.filter((p) => p.phase === "El Nino").map((p) => p.year);
      const allYears = h.comp.points.map((p) => p.year);
      const nino = onsetYears(h.all, v.seasonFor, ninoYears);
      const all = onsetYears(h.all, v.seasonFor, allYears);
      const ns = summarise(nino);
      const shift = medianShift(nino, all);
      if (ns.n < 5) return;
      draw({ pts: ns.byDay, n: ns.n });
      ensoBox.append(el("p", { class: "sig", style: "margin-top:10px" },
        shift == null ? `Too few El Niño years with a clear start to compare.`
          : shift === 0 ? `In El Niño years the rains started at about the usual time (median of ${ns.n} El Niño years vs all years since 1950).`
            : `In El Niño years the rains started a median ${Math.abs(shift)} days ${shift > 0 ? "later" : "earlier"} than in all years since 1950 (${ns.n} El Niño years). False starts: ${Math.round(ns.falseStartPct)}% of El Niño years.`));
      ensoBox.append(more("Table", tableView(["Season", "El Niño", "Start of rains", "False start"],
        all.filter((y) => y.complete).reverse().map((y) => [String(y.year), ninoYears.includes(y.year) ? "yes" : "", y.onset != null ? fromDay(v.seasonFor(y.year).plant + y.onset) : "none in window", y.falseStart ? "yes" : ""]))));
    }).catch((err) => {
      if (!v.alive()) return;
      ensoBox.replaceChildren(note(`Could not load past seasons: ${(err as Error).message}`, "note error"));
    });
  };
  if (v.autoHistory) runHistory();
  else {
    const btn = el("button", { class: "cta", type: "button", style: "margin-top:10px" }, "Compare with El Niño years");
    btn.addEventListener("click", runHistory);
    ensoBox.append(btn);
  }
}
