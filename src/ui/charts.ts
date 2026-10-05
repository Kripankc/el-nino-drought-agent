import * as Plot from "@observablehq/plot";
import { Day, toDate } from "../lib/dates";

/** Resolve CSS custom properties to concrete colours (SVG attributes cannot use var()). */
export function theme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  return {
    ink: v("--ink"), ink2: v("--ink-2"), ink3: v("--ink-3"), line: v("--line"), line2: v("--line-2"),
    panel: v("--panel"), raised: v("--raised"),
    rain: v("--rain"), need: v("--need"), cmp: v("--cmp"), band: v("--band"), heat: v("--heat"), cool: v("--cool"),
    sprout: v("--sprout"), irrig: v("--irrig"), dry: v("--dry"), wet: v("--wet"),
    nino: v("--nino"), nina: v("--nina"), neutral: v("--neutral"), stage: v("--stage"), stageMid: v("--stage-mid"),
  };
}

export type Key = { label: string; color: string; kind: "line" | "band" | "dot" };

export function keys(items: Key[]): HTMLElement {
  const el = document.createElement("div");
  el.className = "keys";
  for (const it of items) {
    const s = document.createElement("span");
    const k = document.createElement("i");
    k.className = it.kind === "line" ? "k-line" : it.kind === "band" ? "k-band" : "k-dot";
    if (it.kind === "line") k.style.borderTopColor = it.color;
    else k.style.background = it.color;
    s.append(k, document.createTextNode(it.label));
    el.append(s);
  }
  return el;
}

/** Table view so every plotted value is readable without hovering. */
export function tableView(columns: string[], rows: (string | number | null)[][]): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "scroll";
  const d = document.createElement("details");
  d.className = "tbl";
  d.open = true;
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
      td.textContent = v == null ? "–" : String(v);
      if (i > 0) td.className = "num";
    });
  }
  wrap.append(t);
  d.append(wrap);
  return d;
}

export const r1 = (x: number | null | undefined) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10) / 10);

function base(width: number, height: number, unit: string): Plot.PlotOptions {
  const t = theme();
  return {
    width, height, marginLeft: 38, marginRight: 8, marginTop: 18, marginBottom: 34,
    style: { background: "transparent", color: t.ink3, fontSize: "11px", fontFamily: "inherit" },
    x: { type: "utc", label: null, tickSize: 0, tickPadding: 8 },
    y: { grid: true, label: unit, labelAnchor: "top", labelArrow: "none", labelOffset: 36, tickSize: 0, tickPadding: 6, nice: true },
  };
}

// ------------------------------------------------------------ time series
export interface SeriesPoint { day: Day; y: number | null }
export interface BandPoint { day: Day; lo: number; mid: number; hi: number }

export function timeChart(opts: {
  width: number; height?: number; unit: string;
  band?: BandPoint[]; bandLabel?: string;
  lines: { label: string; color: string; points: SeriesPoint[]; width?: number; dash?: string }[];
  hline?: { y: number; label: string };
  vline?: { day: Day; label: string };
}): SVGSVGElement | HTMLElement {
  const t = theme();
  const marks: Plot.Markish[] = [];
  const band = (opts.band ?? []).map((b) => ({ ...b, date: toDate(b.day) }));
  if (band.length) {
    marks.push(Plot.areaY(band, { x: "date", y1: "lo", y2: "hi", fill: t.band, fillOpacity: 0.16, curve: "monotone-x" }));
    marks.push(Plot.lineY(band, { x: "date", y: "mid", stroke: t.band, strokeWidth: 1, strokeOpacity: 0.8, curve: "monotone-x" }));
  }
  if (opts.hline) {
    const days = [...band.map((b) => b.day), ...opts.lines.flatMap((l) => l.points.map((p) => p.day))];
    marks.push(Plot.ruleY([opts.hline.y], { stroke: t.heat, strokeWidth: 1, strokeOpacity: 0.9 }));
    if (days.length) {
      const x1 = toDate(Math.max(...days));
      marks.push(Plot.text([{ x: x1, y: opts.hline.y, l: opts.hline.label }], { x: "x", y: "y", dy: -7, text: "l", fill: t.heat, textAnchor: "end", fontWeight: 600 }));
    }
  }
  if (opts.vline) {
    marks.push(Plot.ruleX([toDate(opts.vline.day)], { stroke: t.ink3, strokeWidth: 1 }));
    marks.push(Plot.text([{ d: toDate(opts.vline.day), l: opts.vline.label }], { x: "d", frameAnchor: "top", dy: -10, text: "l", fill: t.ink3 }));
  }
  const rows: Record<string, any>[] = [];
  for (const ln of opts.lines) {
    const pts = ln.points.filter((p) => p.y != null).map((p) => ({ date: toDate(p.day), y: p.y as number, s: ln.label }));
    marks.push(Plot.lineY(pts, { x: "date", y: "y", stroke: ln.color, strokeWidth: ln.width ?? 2, strokeLinecap: "round", strokeLinejoin: "round", strokeDasharray: ln.dash }));
    if (pts.length) marks.push(Plot.dot([pts[pts.length - 1]], { x: "date", y: "y", r: 3.5, fill: ln.color, stroke: t.panel, strokeWidth: 1.5 }));
    rows.push(...pts);
  }
  const byDate = new Map<number, Record<string, any>>();
  const add = (date: Date, k: string, v: number | null) => {
    const r = byDate.get(date.getTime()) ?? { date };
    r[k] = v;
    byDate.set(date.getTime(), r);
  };
  rows.forEach((r) => add(r.date, r.s, r.y));
  band.forEach((b) => add(b.date, "_band", null));
  const tipRows = [...byDate.values()].sort((a, b) => a.date - b.date);
  const bandByDate = new Map(band.map((b) => [b.date.getTime(), b]));
  marks.push(Plot.ruleX(tipRows, Plot.pointerX({ x: "date", stroke: t.ink3, strokeOpacity: 0.5 })));
  marks.push(Plot.tip(tipRows, Plot.pointerX({
    x: "date",
    title: (r: any) => {
      const lines = [r.date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })];
      for (const ln of opts.lines) if (r[ln.label] != null) lines.push(`${ln.label}: ${r1(r[ln.label])} ${opts.unit}`);
      const b = bandByDate.get(r.date.getTime());
      if (b) lines.push(`${opts.bandLabel ?? "Normal"}: ${r1(b.lo)}–${r1(b.hi)} ${opts.unit}`);
      return lines.join("\n");
    },
    fill: t.panel, stroke: t.line, fontSize: 12, lineHeight: 1.3,
  })));
  return Plot.plot({ ...base(opts.width, opts.height ?? 220, opts.unit), marks });
}

/** Small line with its normal band and the latest point; no axes. */
export function sparkline(width: number, points: SeriesPoint[], band: BandPoint[], color: string): SVGSVGElement | HTMLElement {
  const t = theme();
  const pts = points.filter((p) => p.y != null).map((p) => ({ date: toDate(p.day), y: p.y as number }));
  const b = band.map((x) => ({ ...x, date: toDate(x.day) }));
  return Plot.plot({
    width, height: 46, margin: 3, marginRight: 6,
    style: { background: "transparent" },
    x: { type: "utc", axis: null }, y: { axis: null, nice: false },
    marks: [
      Plot.areaY(b, { x: "date", y1: "lo", y2: "hi", fill: t.band, fillOpacity: 0.18, curve: "monotone-x" }),
      Plot.lineY(pts, { x: "date", y: "y", stroke: color, strokeWidth: 1.5 }),
      pts.length ? Plot.dot([pts[pts.length - 1]], { x: "date", y: "y", r: 3, fill: color, stroke: t.panel, strokeWidth: 1.5 }) : null,
    ],
  });
}

// ------------------------------------------------------------ ENSO
export function ensoArea(width: number, series: { date: Date; v: number }[], mark?: Date): SVGSVGElement | HTMLElement {
  const t = theme();
  return Plot.plot({
    ...base(width, 190, "°C"),
    y: { domain: [-3, 3], grid: true, label: "°C", labelAnchor: "top", labelArrow: "none", tickSize: 0, ticks: [-2, -1, 0, 1, 2] },
    marks: [
      Plot.areaY(series, { x: "date", y1: 0.5, y2: (d: any) => Math.max(d.v, 0.5), fill: t.nino, fillOpacity: 0.85, curve: "step" }),
      Plot.areaY(series, { x: "date", y1: -0.5, y2: (d: any) => Math.min(d.v, -0.5), fill: t.nina, fillOpacity: 0.85, curve: "step" }),
      Plot.lineY(series, { x: "date", y: "v", stroke: t.ink3, strokeWidth: 0.8, curve: "step" }),
      Plot.ruleY([0], { stroke: t.ink3, strokeOpacity: 0.6 }),
      ...(mark ? [Plot.ruleX([mark], { stroke: t.ink, strokeWidth: 1.5 })] : []),
      Plot.tip(series, Plot.pointerX({ x: "date", y: "v", title: (r: any) => `${r.date.toISOString().slice(0, 7)}  ${r.v > 0 ? "+" : ""}${r.v.toFixed(2)} °C`, fill: t.panel, stroke: t.line })),
    ],
  });
}

export function monthBars(width: number, items: { label: string; v: number | null }[]): SVGSVGElement | HTMLElement {
  const t = theme();
  const d = items.filter((x) => x.v != null) as { label: string; v: number }[];
  const col = (v: number) => (v >= 0.5 ? t.nino : v <= -0.5 ? t.nina : t.neutral);
  return Plot.plot({
    width, height: 110, marginTop: 20, marginBottom: 22, marginLeft: 6, marginRight: 6,
    style: { background: "transparent", color: t.ink3, fontSize: "11px", fontFamily: "inherit" },
    x: { type: "band", domain: items.map((x) => x.label), label: null, tickSize: 0, padding: 0.35 },
    y: { axis: null, domain: [Math.min(-0.5, ...d.map((x) => x.v)), Math.max(0.5, ...d.map((x) => x.v))] },
    marks: [
      Plot.ruleY([0], { stroke: t.line }),
      Plot.barY(d, { x: "label", y: "v", fill: (x: any) => col(x.v), rx: 2 }),
      Plot.text(d, { x: "label", y: "v", text: (x: any) => `${x.v > 0 ? "+" : ""}${x.v.toFixed(1)}`, dy: -8, fill: t.ink2, fontWeight: 600 }),
    ],
  });
}

/** Horizontal beeswarm: one row per ENSO phase, one dot per season. */
export function beeswarm(width: number, pts: { year: number; phase: string; v: number }[], unit: string, highlight: number[]): SVGSVGElement | HTMLElement {
  const t = theme();
  const color = (p: string) => (p === "El Nino" ? t.nino : p === "La Nina" ? t.nina : t.neutral);
  const label = (p: string) => (p === "El Nino" ? "El Niño" : p === "La Nina" ? "La Niña" : "Neutral");
  const groups = ["El Niño", "Neutral", "La Niña"];
  const data = pts.map((p) => ({ ...p, g: label(p.phase), hl: highlight.includes(p.year) }));
  const med = groups.map((g) => {
    const vs = data.filter((d) => d.g === g).map((d) => d.v).sort((a, b) => a - b);
    const n = vs.length;
    return { g, m: n ? (n % 2 ? vs[(n - 1) / 2] : (vs[n / 2 - 1] + vs[n / 2]) / 2) : NaN };
  }).filter((d) => Number.isFinite(d.m));
  return Plot.plot({
    width, height: 210, marginLeft: 64, marginRight: 12, marginTop: 8, marginBottom: 28,
    style: { background: "transparent", color: t.ink3, fontSize: "11px", fontFamily: "inherit" },
    fy: { domain: groups, label: null, padding: 0.08, tickSize: 0 },
    x: { label: unit, labelArrow: "none", labelAnchor: "right", tickSize: 0, grid: true, nice: true },
    y: { axis: null },
    marks: [
      Plot.ruleX([0], { stroke: t.ink3, strokeOpacity: 0.6 }),
      Plot.dot(data, Plot.dodgeY("middle", {
        fy: "g", x: "v", r: 3.6, padding: 0.8,
        fill: (d: any) => color(d.phase), stroke: (d: any) => (d.hl ? t.ink : t.panel), strokeWidth: (d: any) => (d.hl ? 2 : 1),
        title: (d: any) => `${d.year} · ${d.g}: ${d.v > 0 ? "+" : ""}${r1(d.v)}${unit === "%" ? "%" : " °C"}`,
      } as any)),
      Plot.tickX(med, { fy: "g", x: "m", stroke: t.ink, strokeWidth: 2, inset: 6 } as any),
    ],
  });
}
