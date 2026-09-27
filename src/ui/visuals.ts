// Small visual building blocks (plain SVG/HTML) used across the report.
import { el } from "./dom";
import { icon } from "./icons";
import { theme } from "./charts";
import { monthName } from "../lib/dates";

const NS = "http://www.w3.org/2000/svg";
function svg(w: number, h: number, label: string): SVGSVGElement {
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", `0 0 ${w} ${h}`);
  s.setAttribute("width", String(w));
  s.setAttribute("height", String(h));
  s.setAttribute("role", "img");
  s.setAttribute("aria-label", label);
  return s;
}
function node<K extends keyof SVGElementTagNameMap>(parent: Element, tag: K, attrs: Record<string, string | number>, text?: string) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text != null) e.textContent = text;
  parent.append(e);
  return e;
}

export type Tone = "good" | "watch" | "concern" | "severe" | "neutral";
export const TONE_LABEL: Record<Tone, string> = { good: "Normal", watch: "Watch", concern: "Concern", severe: "Severe", neutral: "" };
export const TONE_ICON: Record<Tone, string> = { good: "check", watch: "info", concern: "alert", severe: "alert", neutral: "info" };

// ------------------------------------------------------------------ ring
/** Progress ring (0-1) with a big centre label. */
export function ring(frac: number, centre: string, color: string, size = 76): SVGSVGElement {
  const t = theme();
  const s = svg(size, size, `${Math.round(frac * 100)}%`);
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  node(s, "circle", { cx: size / 2, cy: size / 2, r, fill: "none", stroke: t.grid, "stroke-width": 8 });
  node(s, "circle", {
    cx: size / 2, cy: size / 2, r, fill: "none", stroke: color, "stroke-width": 8, "stroke-linecap": "round",
    "stroke-dasharray": `${Math.max(0.001, Math.min(1, frac)) * c} ${c}`, transform: `rotate(-90 ${size / 2} ${size / 2})`,
  });
  node(s, "text", { x: size / 2, y: size / 2 + 5, "text-anchor": "middle", "font-size": 15, "font-weight": 650, fill: t.ink }, centre);
  return s;
}

// ------------------------------------------------------------------ meter
/**
 * Percentile meter: a 0-100 track with dry / normal / wet zones and a marker.
 * `lowLabel` / `highLabel` name the ends (e.g. "Dry", "Wet").
 */
export function meter(pct: number, lowLabel: string, highLabel: string, width = 180): SVGSVGElement {
  const t = theme();
  const h = 34;
  const s = svg(width, h, `${Math.round(pct)}th percentile`);
  const x = (p: number) => 4 + (p / 100) * (width - 8);
  node(s, "rect", { x: x(0), y: 8, width: x(20) - x(0) - 1, height: 8, rx: 4, fill: t.dry, "fill-opacity": 0.45 });
  node(s, "rect", { x: x(20) + 1, y: 8, width: x(80) - x(20) - 2, height: 8, rx: 4, fill: t.grid });
  node(s, "rect", { x: x(80) + 1, y: 8, width: x(100) - x(80) - 1, height: 8, rx: 4, fill: t.wet, "fill-opacity": 0.45 });
  node(s, "circle", { cx: x(Math.max(0, Math.min(100, pct))), cy: 12, r: 7, fill: t.ink, stroke: t.surface, "stroke-width": 2.5 });
  node(s, "text", { x: 4, y: 31, "font-size": 10.5, fill: t.ink2 }, lowLabel);
  node(s, "text", { x: width / 2, y: 31, "font-size": 10.5, fill: t.ink2, "text-anchor": "middle" }, "Normal");
  node(s, "text", { x: width - 4, y: 31, "font-size": 10.5, fill: t.ink2, "text-anchor": "end" }, highLabel);
  return s;
}

// ------------------------------------------------------------------ supply vs need
/** Two horizontal bars on one scale: rain received vs crop water need. */
export function supplyNeed(rain: number, need: number, width = 200): SVGSVGElement {
  const t = theme();
  const s = svg(width, 44, `Rain ${Math.round(rain)} mm, need ${Math.round(need)} mm`);
  const max = Math.max(rain, need, 1);
  const bw = (v: number) => Math.max(3, (v / max) * (width - 62));
  node(s, "text", { x: 0, y: 13, "font-size": 11, fill: t.ink2 }, "Rain");
  node(s, "rect", { x: 40, y: 4, width: bw(rain), height: 12, rx: 4, fill: t.this });
  node(s, "text", { x: 40 + bw(rain) + 4, y: 14, "font-size": 11, fill: t.ink }, `${Math.round(rain)}`);
  node(s, "text", { x: 0, y: 35, "font-size": 11, fill: t.ink2 }, "Need");
  node(s, "rect", { x: 40, y: 26, width: bw(need), height: 12, rx: 4, fill: t.need });
  node(s, "text", { x: 40 + bw(need) + 4, y: 36, "font-size": 11, fill: t.ink }, `${Math.round(need)}`);
  return s;
}

// ------------------------------------------------------------------ overview tile
export function tile(opts: {
  ico: string; title: string; visual?: Node; value?: string; caption?: string; tone?: Tone; target?: string;
}): HTMLElement {
  const tone = opts.tone ?? "neutral";
  const t = el(opts.target ? "a" : "div", { class: `tile tone-${tone}`, ...(opts.target ? { href: `#${opts.target}` } : {}) },
    el("div", { class: "tile-head" }, el("span", { class: "tile-ico" }, icon(opts.ico, 18)), el("span", { class: "tile-title" }, opts.title)),
    opts.visual ? el("div", { class: "tile-visual" }, opts.visual) : null,
    opts.value ? el("div", { class: "tile-value" }, opts.value) : null,
    opts.caption ? el("div", { class: "tile-cap" }, opts.caption) : null,
    tone !== "neutral" ? el("div", { class: "tile-tone" }, icon(TONE_ICON[tone], 14), TONE_LABEL[tone]) : null,
  );
  return t;
}

// ------------------------------------------------------------------ crop calendar
export interface CalRow { label: string; share: number | null; windows: { plant: number; mature: number; irrigated: boolean }[]; selected?: boolean }

/** 12-month crop calendar: one row per crop, bars from sowing to maturity, share bar on the left. */
export function cropCalendar(rows: CalRow[], todayDoy: number | null, width: number): SVGSVGElement {
  const t = theme();
  const labelW = Math.min(150, Math.max(96, width * 0.26));
  const shareW = 44;
  const x0 = labelW + shareW + 8;
  const plotW = width - x0 - 6;
  const rowH = 30;
  const top = 22;
  const h = top + rows.length * rowH + 6;
  const s = svg(width, h, "Crop calendar");
  const x = (doy: number) => x0 + ((doy - 1) / 365) * plotW;
  // month grid
  for (let m = 0; m < 12; m++) {
    const d0 = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335][m];
    const d1 = m === 11 ? 366 : [32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335][m];
    if (m % 2 === 0) node(s, "rect", { x: x(d0), y: top - 4, width: x(d1) - x(d0), height: rows.length * rowH + 4, fill: t.grid, "fill-opacity": 0.35 });
    const lbl = plotW < 300 ? monthName(m + 1)[0] : monthName(m + 1);
    node(s, "text", { x: (x(d0) + x(d1)) / 2, y: 12, "text-anchor": "middle", "font-size": 10.5, fill: t.ink2 }, lbl);
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH;
    node(s, "text", { x: 0, y: y + 17, "font-size": 12.5, fill: t.ink, "font-weight": r.selected ? 650 : 400 }, r.label);
    if (r.share != null) {
      node(s, "rect", { x: labelW, y: y + 9, width: shareW - 4, height: 10, rx: 3, fill: t.grid });
      node(s, "rect", { x: labelW, y: y + 9, width: Math.max(2, (shareW - 4) * r.share), height: 10, rx: 3, fill: t.ink2 });
    }
    const n = r.windows.length;
    r.windows.forEach((w, k) => {
      const bh = n > 1 ? 9 : 14;
      const by = y + (n > 1 ? 5 + k * 10 : 7);
      const color = w.irrigated ? t.this : t.sprout;
      const segs: [number, number][] = w.mature >= w.plant ? [[w.plant, w.mature]] : [[w.plant, 366], [1, w.mature]];
      for (const [a, b] of segs) {
        node(s, "rect", { x: x(a), y: by, width: Math.max(3, x(b) - x(a)), height: bh, rx: 4, fill: color, "fill-opacity": r.selected ? 1 : 0.75 });
      }
      node(s, "circle", { cx: x(w.plant), cy: by + bh / 2, r: 3, fill: t.surface });
    });
  });
  if (todayDoy != null) {
    node(s, "line", { x1: x(todayDoy), x2: x(todayDoy), y1: top - 6, y2: h - 2, stroke: t.ink, "stroke-width": 1.5 });
  }
  return s;
}

// ------------------------------------------------------------------ forecast strip
export interface DayCard { date: Date; rain: number; rainHi: number; tmax: number; hot: boolean }

export function forecastStrip(days: DayCard[]): HTMLElement {
  const maxRain = Math.max(10, ...days.map((d) => d.rainHi));
  const wrap = el("div", { class: "fstrip", role: "list" });
  for (const d of days) {
    const wd = d.date.toLocaleDateString("en", { weekday: "short", timeZone: "UTC" });
    const dm = `${d.date.getUTCDate()}/${d.date.getUTCMonth() + 1}`;
    const wet = d.rain >= 1;
    const bar = el("div", { class: "fbar" },
      el("div", { class: "fbar-hi", style: `height:${(d.rainHi / maxRain) * 100}%` }),
      el("div", { class: "fbar-mid", style: `height:${(d.rain / maxRain) * 100}%` }));
    wrap.append(el("div", { class: `fday${d.hot ? " hot" : ""}`, role: "listitem", title: `${dm}: rain ${d.rain.toFixed(1)} mm (up to ${d.rainHi.toFixed(0)} mm), max ${d.tmax.toFixed(0)} °C` },
      el("div", { class: "fwd" }, wd), el("div", { class: "fdm" }, dm),
      el("div", { class: "fico" }, icon(wet ? "rain" : d.tmax >= 30 ? "sun" : "cloud", 22)),
      el("div", { class: "ft" }, `${Math.round(d.tmax)}°`),
      bar,
      el("div", { class: "fmm" }, wet ? `${d.rain < 10 ? d.rain.toFixed(1) : Math.round(d.rain)}` : "0")));
  }
  return wrap;
}

// ------------------------------------------------------------------ outlook tiles
export function outlookTiles(months: { label: string; pct: number | null; tAnom: number | null; inStage?: boolean }[]): HTMLElement {
  const wrap = el("div", { class: "otiles" });
  for (const m of months) {
    const p = m.pct;
    const cls = p == null ? "na" : p <= -20 ? "dry2" : p <= -10 ? "dry1" : p >= 20 ? "wet2" : p >= 10 ? "wet1" : "norm";
    const arrow = p == null ? "minus" : p <= -10 ? "arrowDown" : p >= 10 ? "arrowUp" : "minus";
    const word = p == null ? "n/a" : p <= -10 ? "Drier" : p >= 10 ? "Wetter" : "Near normal";
    wrap.append(el("div", { class: `otile ${cls}${m.inStage ? " stage" : ""}` },
      el("div", { class: "om" }, m.label),
      el("div", { class: "oa" }, icon(arrow, 22)),
      el("div", { class: "ov" }, p == null ? "–" : `${p > 0 ? "+" : ""}${Math.round(p)}%`),
      el("div", { class: "ow" }, word),
      m.tAnom != null ? el("div", { class: "ot" }, `${m.tAnom > 0 ? "+" : ""}${m.tAnom.toFixed(1)}°`) : null,
      m.inStage ? el("div", { class: "os" }, "flowering") : null));
  }
  return wrap;
}

// ------------------------------------------------------------------ pictogram
/** n marks, `on` of them highlighted: e.g. 13 of 19 El Nino seasons were dry. */
export function pictogram(n: number, on: number, onColor: string, offColor: string, label: string): HTMLElement {
  const w = el("div", { class: "picto", role: "img", "aria-label": label });
  for (let i = 0; i < n; i++) {
    const d = icon("drop", 22);
    d.style.color = i < on ? onColor : offColor;
    if (i < on) d.setAttribute("fill", onColor);
    w.append(d);
  }
  return w;
}
