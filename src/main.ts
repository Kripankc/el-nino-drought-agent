import "leaflet/dist/leaflet.css";
import "./styles.css";
import L from "leaflet";
import { Day, fromDay, toDay, todayDay } from "./lib/dates";
import { searchPlace, reversePlace } from "./api/geocode";
import { cropsAt, loadCropParams, loadEnso, LocalCrops, CropParamFile } from "./api/static";
import { era5Daily, era5Windows, lastEra5Day, mergeDaily } from "./api/openmeteo";
import { planClimatology } from "./calc/windows";
import { Calendar, seasonForYear } from "./calc/season";
import { EnsoData, episodeMonths, seasonPhase } from "./calc/enso";
import { S } from "./strings";
import { el } from "./ui/dom";
import { icon } from "./ui/icons";
import { renderReport } from "./ui/sections";

// ------------------------------------------------------------------ state
export interface State {
  lat: number | null;
  lon: number | null;
  name: string | null;
  date: Day;
  crop: string | null;   // GGCMI key, e.g. "mai_rf"
  cmp: number | null;    // planting year of a comparison season
}

const state: State = { lat: null, lon: null, name: null, date: todayDay(), crop: null, cmp: null };

function readUrl() {
  const p = new URLSearchParams(location.search);
  const lat = Number(p.get("lat"));
  const lon = Number(p.get("lon"));
  if (p.has("lat") && p.has("lon") && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) { state.lat = lat; state.lon = lon; }
  const d = p.get("date");
  if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) state.date = Math.min(toDay(d), todayDay());
  state.crop = p.get("crop");
  state.cmp = p.get("cmp") ? Number(p.get("cmp")) : null;
  state.name = p.get("name");
}

function writeUrl() {
  const p = new URLSearchParams();
  if (state.lat != null && state.lon != null) { p.set("lat", state.lat.toFixed(4)); p.set("lon", state.lon.toFixed(4)); }
  if (state.name) p.set("name", state.name);
  if (state.date !== todayDay()) p.set("date", fromDay(state.date));
  if (state.crop) p.set("crop", state.crop);
  if (state.cmp) p.set("cmp", String(state.cmp));
  const qs = p.toString();
  history.replaceState(null, "", qs ? `${location.pathname}?${qs}` : location.pathname);
}

// ------------------------------------------------------------------ DOM
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const form = $<HTMLFormElement>("search");
const q = $<HTMLInputElement>("q");
const dateIn = $<HTMLInputElement>("date");
const results = $<HTMLUListElement>("results");
const statusEl = $<HTMLDivElement>("status");
const report = $<HTMLElement>("report");
const panel = $<HTMLElement>("panel");

// Crop and comparison selects live in the report header; main.ts owns them.
const cropSel = el("select", { id: "crop", disabled: "" });
const cmpSel = el("select", { id: "cmp", disabled: "" }, el("option", { value: "" }, "None"));
const fields = el("div", { class: "fields" },
  el("label", { class: "field" }, el("span", {}, "Crop"), cropSel),
  el("label", { class: "field" }, el("span", {}, "Compare season"), cmpSel));

export function setStatus(msg: string | null, isError = false) {
  statusEl.hidden = msg == null;
  statusEl.textContent = msg ?? "";
  statusEl.classList.toggle("error", isError);
}

// ------------------------------------------------------------------ map
const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
const map = L.map("map", { worldCopyJump: true, zoomControl: false }).setView([15, 20], 3);
L.control.zoom({ position: "bottomright" }).addTo(map);
// Basemaps: Esri tile services, no API key needed. If tiles keep failing,
// fall back to the standard OpenStreetMap tiles.
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const esriAttr = 'Tiles &copy; <a href="https://www.esri.com">Esri</a>, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const canvas = dark ? "Dark_Gray" : "Light_Gray";
const base = {
  map: L.layerGroup([
    L.tileLayer(`${ESRI}/Canvas/World_${canvas}_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, attribution: esriAttr }),
    L.tileLayer(`${ESRI}/Canvas/World_${canvas}_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16 }),
  ]),
  sat: L.layerGroup([
    L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 18, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" }),
    L.tileLayer(`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 18 }),
  ]),
};
let tileErrors = 0;
const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
});
base.map.eachLayer((l) => (l as L.TileLayer).on("tileerror", () => {
  if (++tileErrors === 4 && map.hasLayer(base.map)) { base.map.clearLayers(); base.map.addLayer(osm); }
}));
map.setMaxZoom(18);
base.map.addTo(map);
document.querySelectorAll<HTMLButtonElement>(".layers button").forEach((b) => b.addEventListener("click", () => {
  const k = b.dataset.layer as "map" | "sat";
  (Object.keys(base) as ("map" | "sat")[]).forEach((x) => (x === k ? base[x].addTo(map) : base[x].remove()));
  document.querySelectorAll(".layers button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
}));

let marker: L.CircleMarker | null = null;
function placeMarker(lat: number, lon: number, zoom?: number) {
  const c = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#1f5fd1";
  if (marker) marker.setLatLng([lat, lon]);
  else marker = L.circleMarker([lat, lon], { radius: 7, color: "#ffffff", weight: 3, fillColor: c, fillOpacity: 1 }).addTo(map);
  if (zoom) map.flyTo([lat, lon], zoom, { duration: 0.8 });
}

map.on("click", (e: L.LeafletMouseEvent) => {
  const lon = ((((e.latlng.lng + 180) % 360) + 360) % 360) - 180;
  choose(e.latlng.lat, lon, null);
});

async function choose(lat: number, lon: number, name: string | null) {
  state.lat = lat; state.lon = lon; state.name = name; state.cmp = null;
  placeMarker(lat, lon);
  results.replaceChildren();
  if (window.innerWidth <= 900) panel.scrollIntoView({ behavior: "smooth" });
  if (!name) {
    reversePlace(lat, lon).then((n) => {
      if (n && state.lat === lat && state.lon === lon && state.name == null) {
        state.name = n; writeUrl();
        const h = document.getElementById("place-name");
        if (h) h.textContent = n;
      }
    });
  }
  await load();
}

// ------------------------------------------------------------------ search
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = q.value.trim();
  if (!text) return;
  const m = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (m && Math.abs(Number(m[1])) <= 90 && Math.abs(Number(m[2])) <= 180) {
    placeMarker(Number(m[1]), Number(m[2]), 9);
    return choose(Number(m[1]), Number(m[2]), null);
  }
  try {
    const places = await searchPlace(text);
    results.replaceChildren();
    if (!places.length) { results.append(el("li", {}, el("button", { type: "button", disabled: "" }, el("span", { class: "r-sub" }, "No place found. Try a nearby town, or click the map.")))); return; }
    for (const p of places) {
      const parts = p.name.split(",").map((x) => x.trim());
      const b = el("button", { type: "button", role: "option" }, el("span", { class: "r-main" }, parts[0]), el("span", { class: "r-sub" }, parts.slice(1).join(", ")));
      b.addEventListener("click", () => { q.value = parts[0]; placeMarker(p.lat, p.lon, 9); choose(p.lat, p.lon, parts.slice(0, 3).join(", ")); });
      results.append(el("li", {}, b));
    }
  } catch (err) {
    setStatus((err as Error).message, true);
  }
});
document.addEventListener("click", (e) => { if (!form.contains(e.target as Node)) results.replaceChildren(); });

dateIn.max = fromDay(todayDay());
dateIn.addEventListener("change", () => {
  if (!dateIn.value) return;
  state.date = Math.min(toDay(dateIn.value), todayDay());
  if (state.lat != null) load();
});
cropSel.addEventListener("change", () => { state.crop = cropSel.value; state.cmp = null; load(); });
cmpSel.addEventListener("change", () => { state.cmp = cmpSel.value ? Number(cmpSel.value) : null; load(); });

// ------------------------------------------------------------------ menus
function fillCropMenu(local: LocalCrops, params: CropParamFile): string | null {
  const keys = Object.keys(local.calendars);
  const areaOf = (code: string) => local.crops.find((c) => c.ggcmi.includes(code))?.ha ?? 0;
  keys.sort((a, b) => areaOf(b.slice(0, 3)) - areaOf(a.slice(0, 3)) || (a.endsWith("_rf") ? -1 : 1));
  cropSel.replaceChildren();
  if (!keys.length) {
    cropSel.append(el("option", { value: "" }, "No crop calendar here"));
    cropSel.disabled = true;
    return null;
  }
  for (const k of keys) {
    const code = k.slice(0, 3);
    cropSel.append(el("option", { value: k }, `${params.ggcmi_labels[code] ?? code}, ${k.endsWith("_ir") ? "irrigated" : "rainfed"}`));
  }
  cropSel.disabled = false;
  const pick = state.crop && keys.includes(state.crop) ? state.crop : keys[0];
  cropSel.value = pick;
  return pick;
}

function fillCmpMenu(cal: Calendar, enso: EnsoData | null) {
  cmpSel.replaceChildren(el("option", { value: "" }, "None"));
  let lastComplete = new Date().getUTCFullYear();
  while (seasonForYear(cal, lastComplete).harvest > lastEra5Day()) lastComplete--;
  const years: number[] = [];
  for (let y = lastComplete; y >= 1950; y--) years.push(y);
  const label = (y: number) => {
    const s = seasonForYear(cal, y);
    return new Date(s.harvest * 86_400_000).getUTCFullYear() === y ? String(y) : `${y}–${String(y + 1).slice(2)}`;
  };
  if (enso) {
    const months = episodeMonths(enso);
    const nino = years.filter((y) => seasonPhase(months, seasonForYear(cal, y)) === "El Nino");
    const og1 = el("optgroup", { label: "El Niño seasons" });
    nino.forEach((y) => og1.append(el("option", { value: String(y) }, label(y))));
    const og2 = el("optgroup", { label: "All seasons" });
    years.forEach((y) => og2.append(el("option", { value: String(y) }, label(y))));
    cmpSel.append(og1, og2);
  } else years.forEach((y) => cmpSel.append(el("option", { value: String(y) }, label(y))));
  if (state.cmp) cmpSel.value = String(state.cmp);
  cmpSel.disabled = false;
}

// ------------------------------------------------------------------ intro
const EXAMPLES: { n: string; c: string; lat: number; lon: number }[] = [
  { n: "Mazabuka, Zambia", c: "Maize · Southern Africa", lat: -16.25, lon: 27.65 },
  { n: "Chitwan, Nepal", c: "Rice · South Asia", lat: 27.6, lon: 84.45 },
  { n: "Ludhiana, Punjab, India", c: "Wheat and rice", lat: 30.9, lon: 75.85 },
  { n: "Kano, Nigeria", c: "Sorghum and millet · Sahel", lat: 12.0, lon: 8.52 },
  { n: "Story County, Iowa, USA", c: "Maize and soybean", lat: 41.9, lon: -93.4 },
];

function renderIntro() {
  const list = el("ul", { class: "examples" });
  for (const x of EXAMPLES) {
    const b = el("button", { type: "button" }, el("span", {}, el("span", { class: "ex-n" }, x.n), el("br"), el("span", { class: "ex-c" }, x.c)), icon("arrowUp", 16, "ex-arrow"));
    (b.lastElementChild as SVGElement).style.transform = "rotate(90deg)";
    b.addEventListener("click", () => { placeMarker(x.lat, x.lon, 8); choose(x.lat, x.lon, x.n); });
    list.append(el("li", {}, b));
  }
  const feat = (ico: string, t: string, d: string) => el("div", { class: "feature" }, icon(ico, 18), el("div", {}, el("b", {}, t), d));
  report.replaceChildren(el("div", { class: "intro" },
    el("div", { class: "eyebrow" }, "Open climate data for farmers"),
    el("h1", {}, "Rain, heat and El Niño for any farm"),
    el("p", { class: "lead" }, "Search a place or click the map. See this season against normal, what the crop needs, the next weeks and months, and how past El Niño years went there."),
    el("h2", {}, "Try a place"),
    list,
    el("div", { class: "features" },
      feat("drop", "Season water balance", "Rain since sowing against the crop's water need and the 1991–2020 normal."),
      feat("rain", "Forecasts", "15-day ECMWF ensemble and 7-month seasonal outlook."),
      feat("wave", "El Niño history", "Every season since 1950 at this location, by NOAA ENSO episode.")),
    el("div", { class: "panel-foot" }, el("p", {}, "Data: ERA5, ECMWF, NOAA CPC, CROPGRIDS, GGCMI, FAO-56. ", el("a", { href: "methods.html" }, "Methods and sources")))));
}

// ------------------------------------------------------------------ load
let run = 0;

async function load() {
  if (state.lat == null || state.lon == null) return;
  const my = ++run;
  const alive = () => my === run;
  writeUrl();
  dateIn.value = fromDay(state.date);
  report.classList.add("loading");
  const lat = state.lat;
  const lon = state.lon;
  try {
    setStatus(S.status.crops);
    const [params, enso, local] = await Promise.all([
      loadCropParams(),
      loadEnso().catch(() => null),
      cropsAt(lat, lon).catch(() => null),
    ]);
    if (!alive()) return;
    const localCrops: LocalCrops = local ?? { crops: [], totalHa: 0, cellKm2: 0, calendars: {} };
    const cropKey = fillCropMenu(localCrops, params);
    state.crop = cropKey;
    writeUrl();

    const cal: Calendar | null = cropKey ? { plantDoy: localCrops.calendars[cropKey][0], maturityDoy: localCrops.calendars[cropKey][1] } : null;

    // 1991-2020 normals: only the windows this view needs (see calc/windows.ts)
    setStatus(S.status.clim);
    const today = todayDay();
    const D = Math.min(state.date, today);
    const past = D < today - 7;
    const plan = planClimatology(cal, past ? D : lastEra5Day(), past);
    const st = (m: string) => { if (alive()) setStatus(m); };
    const [grid, rainHeat, soilAir] = await Promise.all([
      era5Daily(lat, lon, lastEra5Day() - 1, lastEra5Day(), ["precip"], st).then((r) => r.grid),
      era5Windows(lat, lon, plan.rainHeat, ["precip", "tmax"], st),
      era5Windows(lat, lon, plan.soilAir, ["et0", "rh", "sm"], st),
    ]);
    const clim = { data: mergeDaily([rainHeat, soilAir]), grid };
    if (!alive()) return;

    if (cal) fillCmpMenu(cal, enso);
    else { cmpSel.replaceChildren(el("option", { value: "" }, "None")); cmpSel.disabled = true; }

    report.classList.remove("loading");
    await renderReport({
      root: report, state, params, enso, local: localCrops, cropsLoaded: local != null,
      cropKey, cal, clim: clim.data, grid: clim.grid, fields, alive,
      setStatus: (m, err) => { if (alive()) setStatus(m, err); },
    });
  } catch (err) {
    console.error(err);
    if (alive()) setStatus(`Could not load data: ${(err as Error).message}`, true);
  } finally {
    if (alive()) report.classList.remove("loading");
  }
}

// ------------------------------------------------------------------ boot
readUrl();
dateIn.value = fromDay(state.date);
if (state.lat != null && state.lon != null) {
  placeMarker(state.lat, state.lon, 8);
  load();
} else {
  renderIntro();
}
