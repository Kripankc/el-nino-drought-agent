// Tiny DOM helpers. Untrusted text (place names, API strings) always goes in via textContent.
import { icon } from "./icons";

type Child = Node | string | null | undefined | false;

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

/**
 * A section card: icon + title, and an (i) button that reveals `info` panel.
 * Returns the section; append content to it. Add explanatory text with `info()`.
 */
export interface Block { sec: HTMLElement; body: HTMLElement; info: (...nodes: Child[]) => void }

export function block(parent: HTMLElement, title: string, opts: { id?: string; icon?: string } = {}): Block {
  const id = opts.id ?? `s${++uid}`;
  const panel = el("div", { class: "info-panel", id: `${id}-info`, hidden: "" });
  const btn = el("button", { class: "info-btn", type: "button", "aria-expanded": "false", "aria-controls": `${id}-info`, "aria-label": `About: ${title}`, title: "More information" }, icon("info", 20));
  btn.addEventListener("click", () => {
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open));
    panel.hidden = open;
    if (!open) repaintAll();
  });
  const head = el("div", { class: "block-head" },
    opts.icon ? el("span", { class: "block-ico" }, icon(opts.icon, 22)) : null,
    el("h2", {}, title), btn);
  btn.hidden = true; // shown once info is added
  const body = el("div", { class: "block-body" });
  const sec = el("section", { class: "block", id }, head, panel, body);
  parent.append(sec);
  return {
    sec, body,
    info: (...nodes: Child[]) => {
      btn.hidden = false;
      for (const n of nodes) if (n != null && n !== false) panel.append(typeof n === "string" ? el("p", {}, n) : n);
    },
  };
}

/** Collapsible "show more" area (details/summary), repaints charts when opened. */
export function more(label: string, ...children: Child[]): HTMLDetailsElement {
  const d = el("details", { class: "more" }, el("summary", {}, label), ...children);
  d.addEventListener("toggle", () => { if (d.open) repaintAll(); });
  return d;
}

export function note(text: string, cls = "note"): HTMLElement {
  return el("p", { class: cls }, text);
}

export function srcLine(text: string): HTMLElement {
  return el("p", { class: "src" }, text);
}

// Charts are re-drawn at the container width on resize, on colour-scheme change
// and when a hidden container is opened.
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
  if (!cw && r.host.childElementCount) return; // hidden: keep, redraw when shown
  const w = Math.max(260, Math.floor(cw || 600));
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
  timer = window.setTimeout(repaintAll, 200);
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
