// Custom visual components (plain SVG/HTML).
import { el } from "./dom";
import { theme } from "./charts";
import { Day, monthName } from "../lib/dates";

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
function add(parent: Element, tag: string, a: Record<string, string | number>, text?: string) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(a)) e.setAttribute(k, String(v));
  if (text != null) e.textContent = text;
  parent.append(e);
  return e;
}

// ------------------------------------------------------------------ status
export type Status = "good" | "warn" | "bad" | "none";

export function pctStatus(p: number | null, low = "Below normal", high = "Above normal"): { s: Status; word: string } {
  if (p == null) return { s: "none", word: "" };
  if (p < 10) return { s: "bad", word: `Well ${low.toLowerCase()}` };
  if (p < 25) return { s: "warn", word: low };
  if (p > 90) return { s: "warn", word: `Well ${high.toLowerCase()}` };
  if (p > 75) return { s: "good", word: high };
  return { s: "good", word: "Normal" };
}

export function statusTag(s: Status, word: string): HTMLElement | null {
  return word ? el("div", { class: `st ${s === "none" ? "" : s}` }, word) : null;
}

// ------------------------------------------------------------------ percentile bar
/** Thin percentile bar: 10th-90th normal zone, marker at the value. */
export function pctBar(pct: number, width: number, lowLabel = "Dry", highLabel = "Wet"): SVGSVGElement {
  const t = theme();
  const h = 26;
  const s = svg(width, h, `${Math.round(pct)}th percentile`);
  const x = (p: number) => 5 + (p / 100) * (width - 10);
  add(s, "rect", { x: x(0), y: 6, width: x(100) - x(0), height: 4, rx: 2, fill: t.line2 });
  add(s, "rect", { x: x(10), y: 6, width: x(90) - x(10), height: 4, rx: 2, fill: t.line });
  add(s, "circle", { cx: x(Math.max(0, Math.min(100, pct))), cy: 8, r: 5, fill: t.ink, stroke: t.panel, "stroke-width": 2 });
  add(s, "text", { x: x(0), y: 24, "font-size": 10.5, fill: t.ink3 }, lowLabel);
  add(s, "text", { x: x(100), y: 24, "font-size": 10.5, fill: t.ink3, "text-anchor": "end" }, highLabel);
  return s;
}

/** Rain supplied vs crop need as two thin bars on one scale. */
export function needBars(rain: number, need: number, width: number): SVGSVGElement {
  const t = theme();
  const s = svg(width, 34, `Effective rain ${Math.round(rain)} mm, crop need ${Math.round(need)} mm`);
  const max = Math.max(rain, need, 1);
  const w = (v: number) => Math.max(2, (v / max) * (width - 44));
  add(s, "rect", { x: 0, y: 3, width: w(rain), height: 6, rx: 3, fill: t.rain });
  add(s, "text", { x: w(rain) + 6, y: 10, "font-size": 10.5, fill: t.ink2 }, `${Math.round(rain)}`);
  add(s, "rect", { x: 0, y: 19, width: w(need), height: 6, rx: 3, fill: t.need });
  add(s, "text", { x: w(need) + 6, y: 26, "font-size": 10.5, fill: t.ink2 }, `${Math.round(need)}`);
  return s;
}

// ------------------------------------------------------------------ metric
export function metric(o: { label: string; value: string; unit?: string; ctx?: string; viz?: Node | null; status?: HTMLElement | null }): HTMLElement {
  return el("div", { class: "metric" },
    el("div", { class: "m-label" }, o.label),
    el("div", { class: "m-value" }, o.value, o.unit ? el("span", { class: "m-unit" }, o.unit) : null),
    o.ctx ? el("div", { class: "m-ctx" }, o.ctx) : null,
    o.viz ? el("div", { class: "m-viz" }, o.viz) : null,
    o.status ?? null);
}

// ------------------------------------------------------------------ season line
export interface SeasonLineOpts {
  plant: Day; harvest: Day; bounds: number[] | null; names: string[]; today: Day | null;
}

export function seasonLine(o: SeasonLineOpts, width: number): SVGSVGElement {
  const t = theme();
  const H = 40;
  const s = svg(width, H, "Crop stages");
  const L = o.harvest - o.plant;
  const x = (d: Day) => 1 + ((d - o.plant) / L) * (width - 2);
  const bounds = o.bounds ?? [L];
  let prev = 0;
  bounds.forEach((b, i) => {
    const mid = o.bounds && i === 2;
    add(s, "rect", { x: x(o.plant + prev) + (i ? 1 : 0), y: 4, width: Math.max(0, x(o.plant + b) - x(o.plant + prev) - (i ? 1 : 0)), height: 8, rx: i === 0 || i === bounds.length - 1 ? 4 : 0, fill: mid ? t.stageMid : t.stage });
    if (o.bounds) {
      const cx = (x(o.plant + prev) + x(o.plant + b)) / 2;
      const w = x(o.plant + b) - x(o.plant + prev);
      const name = o.names[i];
      if (w > name.length * 6.2) add(s, "text", { x: cx, y: 28, "text-anchor": "middle", "font-size": 11, fill: mid ? t.ink : t.ink3, "font-weight": mid ? 600 : 400 }, name);
    }
    prev = b;
  });
  if (o.today != null && o.today >= o.plant && o.today <= o.harvest) {
    const xm = x(o.today);
    add(s, "line", { x1: xm, x2: xm, y1: 0, y2: 16, stroke: t.ink, "stroke-width": 2, "stroke-linecap": "round" });
  }
  return s;
}

// ------------------------------------------------------------------ crop calendar
export interface CalRow { label: string; share: number | null; windows: { plant: number; mature: number; irrigated: boolean }[]; selected?: boolean; key?: string }

const MONTH_START = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366];

export function cropCalendar(rows: CalRow[], todayDoy: number | null, width: number, onPick?: (key: string) => void): SVGSVGElement {
  const t = theme();
  const labelW = 104;
  const shareW = 36;
  const x0 = labelW + shareW;
  const plotW = width - x0 - 2;
  const rowH = 24;
  const top = 18;
  const h = top + rows.length * rowH + 4;
  const s = svg(width, h, "Crop calendar");
  const x = (doy: number) => x0 + ((doy - 1) / 365) * plotW;
  for (let m = 0; m < 12; m++) {
    add(s, "line", { x1: x(MONTH_START[m]), x2: x(MONTH_START[m]), y1: top - 4, y2: h - 2, stroke: t.line2 });
    add(s, "text", { x: (x(MONTH_START[m]) + x(MONTH_START[m + 1])) / 2, y: 10, "text-anchor": "middle", "font-size": 10.5, fill: t.ink3 }, monthName(m + 1)[0]);
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH;
    add(s, "text", { x: 0, y: y + 15, "font-size": 12.5, fill: r.selected ? t.ink : t.ink2, "font-weight": r.selected ? 600 : 400 }, r.label.length > 15 ? r.label.slice(0, 14) + "…" : r.label);
    if (r.share != null) add(s, "text", { x: labelW + shareW - 8, y: y + 15, "font-size": 11.5, fill: t.ink3, "text-anchor": "end" }, `${Math.round(r.share * 100)}%`);
    const n = r.windows.length;
    r.windows.forEach((w, k) => {
      const bh = n > 1 ? 5 : 8;
      const by = y + (n > 1 ? 5 + k * 7 : 7);
      const color = w.irrigated ? t.irrig : t.sprout;
      const segs: [number, number][] = w.mature >= w.plant ? [[w.plant, w.mature]] : [[w.plant, 366], [1, w.mature]];
      for (const [a, b] of segs) add(s, "rect", { x: x(a), y: by, width: Math.max(3, x(b) - x(a)), height: bh, rx: bh / 2, fill: color, "fill-opacity": r.selected ? 1 : 0.55 });
    });
  });
  if (todayDoy != null) {
    add(s, "line", { x1: x(todayDoy), x2: x(todayDoy), y1: top - 6, y2: h - 2, stroke: t.ink, "stroke-width": 1.25 });
    add(s, "circle", { cx: x(todayDoy), cy: top - 6, r: 2.5, fill: t.ink });
  }
  if (onPick) {
    rows.forEach((r, i) => {
      if (!r.key || r.selected) return;
      const hit = add(s, "rect", { x: 0, y: top + i * rowH, width, height: rowH, fill: "transparent", class: "cal-hit" });
      hit.append(document.createElementNS("http://www.w3.org/2000/svg", "title"));
      hit.firstElementChild!.textContent = `Show ${r.label}`;
      hit.addEventListener("click", () => onPick(r.key!));
    });
  }
  return s;
}

// ------------------------------------------------------------------ outlook strip
function mix(a: string, b: string, f: number): string {
  const pa = a.match(/\w\w/g)!.map((h) => parseInt(h, 16));
  const pb = b.match(/\w\w/g)!.map((h) => parseInt(h, 16));
  return "#" + pa.map((v, i) => Math.round(v + (pb[i] - v) * f).toString(16).padStart(2, "0")).join("");
}

export function divergingColor(pct: number | null): { bg: string; fg: string } {
  const t = theme();
  const mid = t.line2.length === 7 ? t.line2 : "#f1f2f4";
  if (pct == null) return { bg: mid, fg: t.ink3 };
  const f = Math.min(1, Math.abs(pct) / 50);
  const bg = mix(mid, pct < 0 ? t.dry : t.wet, f);
  return { bg, fg: f > 0.55 ? "#ffffff" : t.ink };
}

export function outlookStrip(items: { label: string; pct: number | null; tAnom: number | null; stage: boolean }[], showStage: boolean): HTMLElement {
  const t = theme();
  const g = el("div", { class: "ol" });
  g.style.gridTemplateColumns = `repeat(${items.length}, 1fr)`;
  for (const it of items) {
    const c = divergingColor(it.pct);
    const cell = el("div", { class: "ol-cell", title: `${it.label}: ${it.pct == null ? "normal rain under 10 mm, % not shown" : `${it.pct > 0 ? "+" : ""}${Math.round(it.pct)}% rain vs normal`}` }, it.pct == null ? "–" : `${it.pct > 0 ? "+" : ""}${Math.round(it.pct)}%`);
    cell.style.background = c.bg;
    cell.style.color = c.fg;
    g.append(el("div", {}, cell, el("div", { class: "ol-m" }, it.label),
      it.tAnom != null ? el("div", { class: "ol-t" }, `${it.tAnom > 0 ? "+" : ""}${it.tAnom.toFixed(1)}°`) : null,
      showStage ? el("div", { class: `ol-stage${it.stage ? " on" : ""}` }) : null));
  }
  const grad = el("i", {});
  grad.style.background = `linear-gradient(90deg, ${t.dry}, ${t.line2}, ${t.wet})`;
  const legend = el("div", { class: "ol-legend" },
    el("span", { class: "grad" }, "Drier", grad, "Wetter"),
    showStage ? el("span", { class: "flw" }, "Flowering stage") : null);
  return el("div", {}, g, legend);
}

// ------------------------------------------------------------------ comparison strip
/** Rows of monthly % departures on a shared diverging scale, one column per month. */
export function compareStrip(months: string[], rows: { label: string; values: (number | null)[]; note?: string }[]): HTMLElement {
  const t = theme();
  const g = el("div", { class: "cs" });
  g.style.gridTemplateColumns = `minmax(76px, auto) repeat(${months.length}, minmax(0, 1fr))`;
  g.append(el("span", {}));
  for (const m of months) g.append(el("span", { class: "cs-m" }, m));
  for (const r of rows) {
    g.append(el("span", { class: "cs-l" }, r.label));
    r.values.forEach((v, i) => {
      const c = divergingColor(v);
      const cell = el("span", { class: "cs-c", title: `${r.label}, ${months[i]}: ${v == null ? "no value (little or no rain normally, or outside the season)" : `${v > 0 ? "+" : ""}${Math.round(v)}% vs normal`}` }, v == null ? "–" : `${v > 0 ? "+" : ""}${Math.round(v)}%`);
      cell.style.background = c.bg;
      cell.style.color = c.fg;
      g.append(cell);
    });
  }
  const grad = el("i", {});
  grad.style.background = `linear-gradient(90deg, ${t.dry}, ${t.line2}, ${t.wet})`;
  return el("div", {}, g, el("div", { class: "ol-legend" }, el("span", { class: "grad" }, "Drier", grad, "Wetter")));
}

/** Two thin bars: a value against its normal. */
export function vsNormalBars(value: number, normal: number, width: number, labels: [string, string], color: string): SVGSVGElement {
  const t = theme();
  const s = svg(width, 34, `${labels[0]} ${Math.round(value)}, ${labels[1]} ${Math.round(normal)}`);
  const max = Math.max(value, normal, 1);
  const w = (v: number) => Math.max(2, (v / max) * (width - 92));
  add(s, "rect", { x: 0, y: 3, width: w(value), height: 6, rx: 3, fill: color });
  add(s, "text", { x: w(value) + 6, y: 10, "font-size": 10.5, fill: t.ink2 }, `${Math.round(value)} ${labels[0]}`);
  add(s, "rect", { x: 0, y: 19, width: w(normal), height: 6, rx: 3, fill: t.band });
  add(s, "text", { x: w(normal) + 6, y: 26, "font-size": 10.5, fill: t.ink3 }, `${Math.round(normal)} ${labels[1]}`);
  return s;
}
