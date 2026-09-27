// DOM helpers. Untrusted text (place names, API strings) always goes in via textContent.
import { icon } from "./icons";

export type Child = Node | string | null | undefined | false;

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K, attrs: Record<string, string> = {}, ...children: Child[]
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) e.append(typeof c === "string" ? document.createTextNode(c) : c);
  return e;
}

let uid = 0;

/** A section: title and an "About" toggle that reveals explanatory notes. */
export interface Sec { el: HTMLElement; body: HTMLElement; about: (...nodes: Child[]) => void }

export function section(parent: HTMLElement, title: string): Sec {
  const id = `sec${++uid}`;
  const panel = el("div", { class: "about-panel", id: `${id}-about`, hidden: "" });
  const btn = el("button", { class: "about", type: "button", "aria-expanded": "false", "aria-controls": `${id}-about`, hidden: "" },
    icon("info", 15), "About");
  btn.addEventListener("click", () => {
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open));
    panel.hidden = open;
  });
  const body = el("div", {});
  const s = el("section", { class: "sec", id }, el("div", { class: "sec-h" }, el("h2", {}, title), btn), panel, body);
  parent.append(s);
  return {
    el: s, body,
    about: (...nodes: Child[]) => {
      btn.hidden = false;
      for (const n of nodes) if (n != null && n !== false && n !== "") panel.append(typeof n === "string" ? el("p", {}, n) : n);
    },
  };
}

/** Tabs: returns one panel element per label. */
export function tabs(parent: HTMLElement, labels: string[], initial = 0): HTMLElement[] {
  const bar = el("div", { class: "tabs", role: "tablist" });
  const panels: HTMLElement[] = [];
  const buttons: HTMLButtonElement[] = [];
  labels.forEach((l, i) => {
    const b = el("button", { type: "button", role: "tab", "aria-selected": String(i === initial) }, l);
    const p = el("div", { class: "tabpanel", role: "tabpanel" });
    if (i !== initial) p.hidden = true;
    b.addEventListener("click", () => {
      buttons.forEach((x, k) => x.setAttribute("aria-selected", String(k === i)));
      panels.forEach((x, k) => (x.hidden = k !== i));
      repaintAll();
      const top = bar.getBoundingClientRect().top;
      if (top < 0) bar.scrollIntoView({ block: "start" });
    });
    buttons.push(b);
    panels.push(p);
    bar.append(b);
  });
  parent.append(bar, ...panels);
  return panels;
}

/** Collapsible area (details/summary); charts inside are repainted when opened. */
export function more(label: string, ...children: Child[]): HTMLDetailsElement {
  const d = el("details", { class: "more" }, el("summary", {}, label), ...children);
  d.addEventListener("toggle", () => { if (d.open) repaintAll(); });
  return d;
}

export function note(text: string, cls = "note"): HTMLElement {
  return el("p", { class: cls }, text);
}

export function caption(text: string): HTMLElement {
  return el("p", { class: "caption" }, text);
}

// Charts re-draw at container width on resize, colour-scheme change and when shown.
type Redraw = { host: HTMLElement; draw: (w: number) => Node };
let charts: Redraw[] = [];

export function chart(parent: HTMLElement, draw: (w: number) => Node, cls = "chart"): HTMLElement {
  const host = el("div", { class: cls });
  parent.append(host);
  const r = { host, draw };
  charts.push(r);
  paint(r);
  return host;
}

function paint(r: Redraw) {
  const cw = r.host.clientWidth;
  if (!cw && r.host.childElementCount) return; // hidden: redraw when shown
  const w = Math.max(240, Math.floor(cw || 430));
  r.host.replaceChildren(r.draw(w));
}

export function resetCharts() { charts = []; }

let timer: number | undefined;
export function repaintAll() {
  charts = charts.filter((r) => r.host.isConnected);
  charts.forEach(paint);
}
window.addEventListener("resize", () => {
  clearTimeout(timer);
  timer = window.setTimeout(repaintAll, 150);
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", repaintAll);

export const fmt = {
  mm: (x: number) => `${Math.round(x).toLocaleString("en")} mm`,
  pct: (x: number) => `${x > 0 ? "+" : ""}${Math.round(x)}%`,
  c: (x: number) => `${x.toFixed(1)} °C`,
  dc: (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(1)} °C`,
  ord: (n: number) => {
    const r = Math.round(n);
    const s = r % 100 >= 11 && r % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[r % 10] ?? "th";
    return `${r}${s}`;
  },
};
