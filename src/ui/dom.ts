// Tiny DOM helpers. Untrusted text (place names, API strings) always goes in via textContent.
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K, attrs: Record<string, string> = {}, ...children: (Node | string | null | undefined)[]
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) if (c != null) e.append(typeof c === "string" ? document.createTextNode(c) : c);
  return e;
}

export function block(parent: HTMLElement, title: string, id?: string): HTMLElement {
  const s = el("section", { class: "block", ...(id ? { id } : {}) }, el("h2", {}, title));
  parent.append(s);
  return s;
}

export function note(text: string, cls = "note"): HTMLElement {
  return el("p", { class: cls }, text);
}

export function stat(value: string, label: string): HTMLElement {
  return el("div", { class: "stat" }, el("div", { class: "v" }, value), el("div", { class: "l" }, label));
}

// Charts are re-drawn at the container width on resize and on colour-scheme change.
type Redraw = { host: HTMLElement; draw: (w: number) => Node };
let charts: Redraw[] = [];

export function chart(parent: HTMLElement, draw: (w: number) => Node): HTMLElement {
  const host = el("div", { class: "chart" });
  parent.append(host);
  const r = { host, draw };
  charts.push(r);
  paint(r);
  return host;
}

function paint(r: Redraw) {
  const w = Math.max(280, Math.floor(r.host.clientWidth || r.host.parentElement?.clientWidth || 600));
  r.host.replaceChildren(r.draw(w));
}

export function resetCharts() { charts = []; }

let timer: number | undefined;
function repaintAll() {
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
