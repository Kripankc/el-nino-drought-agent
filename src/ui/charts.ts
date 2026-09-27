import * as Plot from "@observablehq/plot";
import { Day, toDate } from "../lib/dates";

/** Resolve CSS custom properties to concrete colours (SVG attributes cannot use var()). */
export function theme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  return {
    ink: v("--ink"), ink2: v("--ink-2"), muted: v("--muted"), grid: v("--grid"), axis: v("--axis"),
    surface: v("--surface"), this: v("--s-this"), cmp: v("--s-cmp"), need: v("--s-need"),
    band: v("--band"), nino: v("--nino"), nina: v("--nina"), neutral: v("--neutral"),
    dry: v("--dry"), wet: v("--wet"),
  };
}

export type Legend = { label: string; color: string; kind: "line" | "band" | "dot" }[];

export function legend(items: Legend): HTMLElement {
  const el = document.createElement("div");
  el.className = "legend";
  for (const it of items) {
    const s = document.createElement("span");
    const k = document.createElement("i");
    k.className = it.kind === "line" ? "key-line" : it.kind === "band" ? "key-band" : "key-dot";
    if (it.kind === "line") k.style.borderTopColor = it.color;
    else k.style.background = it.color;
    s.append(k, document.createTextNode(it.label));
    el.append(s);
  }
  return el;
}

/** Collapsible table view so every plotted value is readable without hovering. */
export function tableView(columns: string[], rows: (string | number | null)[][], summary = "Show data table"): HTMLElement {
  const d = document.createElement("details");
  d.className = "tbl";
  const s = document.createElement("summary");
  s.textContent = summary;
  const wrap = document.createElement("div");
  wrap.className = "scroll";
  const t = document.createElement("table");
  t.className = "data";
  const head = t.createTHead().insertRow();
  columns.forEach((c, i) => {
    const th = document.createElement("th");
    th.textContent = c;
    if (i > 0) th.className = "num";
    head.append(th);
  });
  const body = t.createTBody();
  for (const r of rows) {
    const tr = body.insertRow();
    r.forEach((v, i) => {
      const td = tr.insertCell();
      td.textContent = v == null ? "–" : typeof v === "number" ? String(v) : v;
      if (i > 0) td.className = "num";
    });
  }
  wrap.append(t);
  d.append(s, wrap);
  return d;
}

const r1 = (x: number | null | undefined) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10) / 10);
export { r1 };

function base(width: number, height: number, yLabel: string, extra: Partial<Plot.PlotOptions> = {}): Plot.PlotOptions {
  const t = theme();
  return {
    width, height, marginLeft: 44, marginRight: 16, marginBottom: 30,
    style: { background: "transparent", color: t.ink2, fontSize: "11px" },
    x: { type: "utc", grid: false, label: null },
    y: { grid: true, label: yLabel, labelArrow: "none" },
    ...extra,
  };
}

// ------------------------------------------------------------ time series
export interface SeriesPoint { day: Day; y: number | null }
export interface BandPoint { day: Day; lo: number; mid: number; hi: number }

export function timeChart(opts: {
  width: number; height?: number; yLabel: string; unit: string;
  band?: BandPoint[]; bandLabel?: string;
  lines: { label: string; color: string; points: SeriesPoint[] }[];
  hline?: { y: number; label: string };
  vline?: { day: Day; label: string };
  zero?: boolean;
}): SVGSVGElement | HTMLElement {
  const t = theme();
  const marks: Plot.Markish[] = [];
  const band = (opts.band ?? []).map((b) => ({ ...b, date: toDate(b.day) }));
  if (band.length) {
    marks.push(Plot.areaY(band, { x: "date", y1: "lo", y2: "hi", fill: t.band, fillOpacity: 0.18, curve: "linear" }));
    marks.push(Plot.lineY(band, { x: "date", y: "mid", stroke: t.band, strokeWidth: 1 }));
  }
  if (opts.zero) marks.push(Plot.ruleY([0], { stroke: t.axis }));
  if (opts.hline) {
    const days = [...(opts.band ?? []).map((b) => b.day), ...opts.lines.flatMap((l) => l.points.map((p) => p.day))];
    marks.push(Plot.ruleY([opts.hline.y], { stroke: t.need, strokeWidth: 1.5 }));
    if (days.length) {
      const x0 = toDate(Math.min(...days));
      marks.push(Plot.text([{ x: x0, y: opts.hline.y, l: opts.hline.label }], { x: "x", y: "y", dy: -7, dx: 2, text: "l", fill: t.ink2, textAnchor: "start" }));
    }
  }
  if (opts.vline) {
    marks.push(Plot.ruleX([toDate(opts.vline.day)], { stroke: t.ink2, strokeWidth: 1 }));
    marks.push(Plot.text([{ d: toDate(opts.vline.day), l: opts.vline.label }], { x: "d", frameAnchor: "top", dy: 6, dx: 4, text: "l", fill: t.ink2, textAnchor: "start" }));
  }
  const rows: Record<string, any>[] = [];
  for (const ln of opts.lines) {
    const pts = ln.points.filter((p) => p.y != null).map((p) => ({ date: toDate(p.day), y: p.y as number, s: ln.label }));
    marks.push(Plot.lineY(pts, { x: "date", y: "y", stroke: ln.color, strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" }));
    rows.push(...pts);
  }
  // One tooltip listing every series at the hovered date
  const byDate = new Map<number, Record<string, any>>();
  const add = (date: Date, k: string, v: number | null) => {
    const key = date.getTime();
    const r = byDate.get(key) ?? { date };
    r[k] = v;
    byDate.set(key, r);
  };
  rows.forEach((r) => add(r.date, r.s, r.y));
  band.forEach((b) => add(b.date, opts.bandLabel ?? "1991–2020 range", null));
  const tipRows = [...byDate.values()].sort((a, b) => a.date - b.date);
  const bandByDate = new Map(band.map((b) => [b.date.getTime(), b]));
  marks.push(Plot.ruleX(tipRows, Plot.pointerX({ x: "date", stroke: t.axis })));
  marks.push(Plot.tip(tipRows, Plot.pointerX({
    x: "date",
    title: (r: any) => {
      const lines = [r.date.toISOString().slice(0, 10)];
      for (const ln of opts.lines) if (r[ln.label] != null) lines.push(`${ln.label}: ${r1(r[ln.label])} ${opts.unit}`);
      const b = bandByDate.get(r.date.getTime());
      if (b) lines.push(`${opts.bandLabel ?? "1991–2020"}: ${r1(b.lo)}–${r1(b.hi)} ${opts.unit} (median ${r1(b.mid)})`);
      return lines.join("\n");
    },
    fill: t.surface, stroke: t.axis, fontSize: 12,
  })));
  return Plot.plot({ ...base(opts.width, opts.height ?? 240, opts.yLabel), marks });
}

// ------------------------------------------------------------ bars
export function anomalyBars(opts: {
  width: number; items: { label: string; value: number | null; note?: string }[]; unit: string; yLabel: string;
}): SVGSVGElement | HTMLElement {
  const t = theme();
  const data = opts.items.filter((d) => d.value != null) as { label: string; value: number; note?: string }[];
  return Plot.plot({
    ...base(opts.width, 220, opts.yLabel, { x: { type: "band", label: null, domain: opts.items.map((d) => d.label), padding: 0.35 } }),
    marks: [
      Plot.ruleY([0], { stroke: t.axis }),
      Plot.barY(data, { x: "label", y: "value", fill: (d: any) => (d.value < 0 ? t.dry : t.wet), rx: 3, insetLeft: 1, insetRight: 1 }),
      Plot.text(data.filter((d) => d.value >= 0), { x: "label", y: "value", text: (d: any) => `+${Math.round(d.value)}${opts.unit}`, dy: -8, fill: t.ink2 }),
      Plot.text(data.filter((d) => d.value < 0), { x: "label", y: "value", text: (d: any) => `${Math.round(d.value)}${opts.unit}`, dy: 9, fill: t.ink2 }),
      Plot.tip(data, Plot.pointerX({ x: "label", y: "value", title: (d: any) => `${d.label}: ${d.value > 0 ? "+" : ""}${r1(d.value)}${opts.unit}${d.note ? "\n" + d.note : ""}`, fill: t.surface, stroke: t.axis })),
    ],
  });
}

// ------------------------------------------------------------ forecast
export function forecastRain(width: number, rows: { day: Day; p10: number; p50: number; p90: number }[]): SVGSVGElement | HTMLElement {
  const t = theme();
  const d = rows.map((r) => ({ ...r, date: toDate(r.day) }));
  return Plot.plot({
    ...base(width, 200, "mm per day", { x: { type: "band", label: null, ticks: d.filter((_, i) => i % 3 === 0).map((r) => r.date), tickFormat: (x: Date) => `${x.getUTCDate()}/${x.getUTCMonth() + 1}`, padding: 0.3 } }),
    marks: [
      Plot.ruleY([0], { stroke: t.axis }),
      Plot.barY(d, { x: "date", y: "p50", fill: t.this, rx: 2 }),
      Plot.ruleX(d, { x: "date", y1: "p10", y2: "p90", stroke: t.ink2, strokeWidth: 1.2 }),
      Plot.tip(d, Plot.pointerX({ x: "date", y: "p50", title: (r: any) => `${r.date.toISOString().slice(0, 10)}\nmedian ${r1(r.p50)} mm (10–90%: ${r1(r.p10)}–${r1(r.p90)} mm)`, fill: t.surface, stroke: t.axis })),
    ],
  });
}

// ------------------------------------------------------------ ENSO
export function ensoTimeline(width: number, series: { date: Date; v: number }[], episodes: { type: string; start: Date; end: Date }[], mark?: Date): SVGSVGElement | HTMLElement {
  const t = theme();
  return Plot.plot({
    ...base(width, 200, "°C"),
    marks: [
      Plot.rectY(episodes, { x1: "start", x2: "end", y1: -3, y2: 3, fill: (e: any) => (e.type === "El Nino" ? t.nino : t.nina), fillOpacity: 0.14 }),
      Plot.ruleY([0.5, -0.5], { stroke: t.grid }),
      Plot.ruleY([0], { stroke: t.axis }),
      Plot.lineY(series, { x: "date", y: "v", stroke: t.ink2, strokeWidth: 1.5 }),
      ...(mark ? [Plot.ruleX([mark], { stroke: t.ink, strokeWidth: 1.5 })] : []),
      Plot.tip(series, Plot.pointerX({ x: "date", y: "v", title: (r: any) => `${r.date.toISOString().slice(0, 7)}: ${r.v > 0 ? "+" : ""}${r.v.toFixed(2)} °C`, fill: t.surface, stroke: t.axis })),
    ],
    y: { domain: [-3, 3], grid: true, label: "°C", labelArrow: "none" },
  });
}

export function compositeDots(width: number, pts: { year: number; phase: string; v: number }[], unit: string, yLabel: string, highlight: number[]): SVGSVGElement | HTMLElement {
  const t = theme();
  const color = (p: string) => (p === "El Nino" ? t.nino : p === "La Nina" ? t.nina : t.neutral);
  const label = (p: string) => (p === "El Nino" ? "El Niño" : p === "La Nina" ? "La Niña" : "Neutral");
  const groups = ["El Niño", "Neutral", "La Niña"];
  const data = pts.map((p) => ({ ...p, g: label(p.phase), hl: highlight.includes(p.year) }));
  const medians = groups.map((g) => {
    const vs = data.filter((d) => d.g === g).map((d) => d.v).sort((a, b) => a - b);
    const n = vs.length;
    return { g, m: n ? (n % 2 ? vs[(n - 1) / 2] : (vs[n / 2 - 1] + vs[n / 2]) / 2) : NaN };
  }).filter((d) => Number.isFinite(d.m));
  return Plot.plot({
    ...base(width, 280, yLabel),
    x: { axis: null },
    fx: { domain: groups, label: null, padding: 0.1 },
    marks: [
      Plot.ruleY([0], { stroke: t.axis }),
      Plot.tickY(medians, { fx: "g", y: "m", stroke: t.ink, strokeWidth: 2 }),
      Plot.dot(data, Plot.dodgeX("middle", {
        fx: "g", y: "v", r: 4.5, padding: 1,
        fill: (d: any) => color(d.phase),
        stroke: (d: any) => (d.hl ? t.ink : t.surface), strokeWidth: (d: any) => (d.hl ? 2.5 : 1.5),
        title: (d: any) => `${d.year} season (${d.g}): ${d.v > 0 ? "+" : ""}${r1(d.v)}${unit}`,
      } as any)),
    ],
  });
}
