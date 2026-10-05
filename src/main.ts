import "leaflet/dist/leaflet.css";
import "./styles.css";
import L from "leaflet";
import { Day, fromDay, toDay, todayDay } from "./lib/dates";
import { searchPlace, reversePlace } from "./api/geocode";
import { cropsAt, loadCropParams, loadEnso, LocalCrops, CropParamFile } from "./api/static";
import { era5Daily, era5Windows, lastEra5Day, mergeDaily } from "./api/openmeteo";
import { planClimatology } from "./calc/windows";
import { Calendar, seasonForYear } from "./calc/season";
import { CropChoice, cropChoices } from "./calc/crops";
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
const details = $<HTMLElement>("details");
const app = $<HTMLElement>("app");

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
const map = L.map("map", { worldCopyJump: true, zoomControl: false }).setView([15, 20], 3);
L.control.zoom({ position: "bottomright" }).addTo(map);
// Basemap: Esri World Imagery with boundaries and place names (no API key).
// If imagery tiles keep failing, fall back to the standard OpenStreetMap tiles.
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const imagery = L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 18, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" });
const labels = L.tileLayer(`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 18, attribution: "Labels &copy; Esri" });
const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
});
let tileErrors = 0;
imagery.on("tileerror", () => {
  if (++tileErrors === 4) { imagery.remove(); labels.remove(); osm.addTo(map); }
});
map.setMaxZoom(18);
imagery.addTo(map);
labels.setZIndex(3).addTo(map);

// Satellite data layers from NASA GIBS (free, no key). For a past date the layer
// shows that date; otherwise the latest available image.
const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
const OVERLAYS: Record<string, { label: string; layer: string; tms: string; maxNative: number; start: string; legend: string; source: string }> = {
  ndvi: { label: "Vegetation (NDVI)", layer: "MODIS_Terra_NDVI_8Day", tms: "GoogleMapsCompatible_Level9", maxNative: 9, start: "2000-03-01",
    legend: "https://gibs.earthdata.nasa.gov/legends/MODIS_NDVI_H.svg", source: "MODIS Terra NDVI, 8-day composite, NASA GIBS" },
  rain: { label: "Rain (IMERG)", layer: "IMERG_Precipitation_Rate", tms: "GoogleMapsCompatible_Level6", maxNative: 6, start: "2000-06-01",
    legend: "https://gibs.earthdata.nasa.gov/legends/GPM_Precipitation_Rate_H.svg", source: "GPM IMERG precipitation rate, daily, NASA GIBS" },
  soil: { label: "Soil moisture (SMAP)", layer: "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", tms: "GoogleMapsCompatible_Level6", maxNative: 6, start: "2015-04-01",
    legend: "https://gibs.earthdata.nasa.gov/legends/SMAP_Analyzed_Soil_Moisture_H.svg", source: "SMAP L4 root-zone soil moisture, daily, NASA GIBS" },
};
const ovSel = $<HTMLSelectElement>("overlay");
const ovInfo = $<HTMLDivElement>("overlay-info");
let overlay: L.TileLayer | null = null;
function setOverlayDate() {
  const past = state.date < todayDay() - 7;
  for (const o of ovSel.options) {
    const def = OVERLAYS[o.value];
    o.disabled = !!def && past && fromDay(state.date) < def.start;
  }
  if (ovSel.selectedOptions[0]?.disabled) ovSel.value = "";
  showOverlay();
}
function showOverlay() {
  overlay?.remove();
  overlay = null;
  const def = OVERLAYS[ovSel.value];
  ovInfo.hidden = !def;
  if (!def) return;
  const past = state.date < todayDay() - 7;
  const time = past ? fromDay(state.date) : "default";
  overlay = L.tileLayer(`${GIBS}/${def.layer}/default/${time}/${def.tms}/{z}/{y}/{x}.png`, {
    maxNativeZoom: def.maxNative, maxZoom: 18, opacity: 0.8, zIndex: 2,
    attribution: 'Data layers: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a>',
  }).addTo(map);
  ovInfo.replaceChildren(
    el("img", { src: def.legend, alt: `${def.label} colour scale`, class: "ov-legend" }),
    el("div", { class: "ov-src" }, `${def.source} · ${past ? fromDay(state.date) : "latest image"}`));
}
for (const [k, v] of Object.entries(OVERLAYS)) ovSel.append(el("option", { value: k }, v.label));
ovSel.addEventListener("change", showOverlay);
setOverlayDate();

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
  state.lat = lat; state.lon = lon; state.name = name; state.cmp = null; state.crop = null;
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
  state.crop = null;   // show the crop growing at the new date
  state.cmp = null;
  setOverlayDate();
  if (state.lat != null) load();
});
cropSel.addEventListener("change", () => { state.crop = cropSel.value; state.cmp = null; load(); });
cmpSel.addEventListener("change", () => { state.cmp = cmpSel.value ? Number(cmpSel.value) : null; load(); });

// ------------------------------------------------------------------ menus
function fillCropMenu(local: LocalCrops, params: CropParamFile): string | null {
  const { options, pick } = cropChoices(local.crops, local.calendars, Math.min(state.date, todayDay()));
  cropSel.replaceChildren();
  if (!options.length) {
    cropSel.append(el("option", { value: "" }, local.totalHa > 0 ? "No crop calendar here" : "No cropland mapped here"));
    cropSel.disabled = true;
    return null;
  }
  const now = options.filter((o) => o.inSeason);
  const later = options.filter((o) => !o.inSeason);
  const opt = (o: CropChoice) => el("option", { value: o.key },
    `${params.ggcmi_labels[o.code] ?? o.code}, ${o.key.endsWith("_ir") ? "irrigated" : "rainfed"} · ${Math.round(o.share * 100)}%`);
  if (now.length) cropSel.append(el("optgroup", { label: "Growing now" }, ...now.map(opt)));
  if (later.length) cropSel.append(el("optgroup", { label: now.length ? "Other crops grown here" : "Crops grown here" }, ...later.map(opt)));
  cropSel.disabled = false;
  const chosen = state.crop && options.some((o) => o.key === state.crop) ? state.crop : pick!;
  cropSel.value = chosen;
  return chosen;
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
  details.replaceChildren(el("div", { class: "details-empty" },
    el("p", {}, "Charts for the season, the next 15 days, the 7-month outlook and El Niño history appear here once you pick a place.")));
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
  details.classList.add("loading");
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
    details.classList.remove("loading");
    await renderReport({
      root: report, state, params, enso, local: localCrops, cropsLoaded: local != null,
      cropKey, cal, clim: clim.data, grid: clim.grid, fields, details, alive,
      pickCrop: (key) => { state.crop = key; state.cmp = null; load(); },
      setStatus: (m, err) => { if (alive()) setStatus(m, err); },
    });
  } catch (err) {
    console.error(err);
    if (alive()) setStatus(`Could not load data: ${(err as Error).message}`, true);
  } finally {
    if (alive()) { report.classList.remove("loading"); details.classList.remove("loading"); }
  }
}

// ------------------------------------------------------------------ resizable layout
// Two drag handles: between the side panel and the right column, and between
// the map and the details below it. Sizes are kept per browser.
const SIZE_KEY = "ensowatch.layout";
function loadSizes(): { left: number; map: number } {
  try { return { left: 0.42, map: 0.46, ...JSON.parse(localStorage.getItem(SIZE_KEY) ?? "{}") }; }
  catch { return { left: 0.42, map: 0.46 }; }
}
const sizes = loadSizes();
function applySizes() {
  app.style.setProperty("--left", `${(sizes.left * 100).toFixed(2)}%`);
  app.style.setProperty("--map", `${(sizes.map * 100).toFixed(2)}%`);
}
let settle: number | undefined;
function afterResize() {
  map.invalidateSize();
  clearTimeout(settle);
  settle = window.setTimeout(() => {
    window.dispatchEvent(new Event("resize")); // charts re-draw at their new width
    try { localStorage.setItem(SIZE_KEY, JSON.stringify(sizes)); } catch { /* private mode */ }
  }, 120);
}
function dragHandle(id: string, axis: "x" | "y") {
  const g = $<HTMLElement>(id);
  const box = () => (axis === "x" ? app : $<HTMLElement>("right")).getBoundingClientRect();
  const set = (frac: number) => {
    if (axis === "x") sizes.left = Math.min(0.7, Math.max(0.25, frac));
    else sizes.map = Math.min(0.85, Math.max(0.15, frac));
    applySizes();
    afterResize();
  };
  g.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    g.setPointerCapture(e.pointerId);
    document.body.classList.add(axis === "x" ? "resizing-x" : "resizing-y");
    const move = (ev: PointerEvent) => {
      const b = box();
      set(axis === "x" ? (ev.clientX - b.left) / b.width : (ev.clientY - b.top) / b.height);
    };
    const up = () => {
      g.removeEventListener("pointermove", move);
      document.body.classList.remove("resizing-x", "resizing-y");
    };
    g.addEventListener("pointermove", move);
    g.addEventListener("pointerup", up, { once: true });
  });
  g.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 0.1 : 0.03;
    const cur = axis === "x" ? sizes.left : sizes.map;
    if ((axis === "x" && e.key === "ArrowLeft") || (axis === "y" && e.key === "ArrowUp")) { set(cur - step); e.preventDefault(); }
    if ((axis === "x" && e.key === "ArrowRight") || (axis === "y" && e.key === "ArrowDown")) { set(cur + step); e.preventDefault(); }
  });
  g.addEventListener("dblclick", () => set(axis === "x" ? 0.42 : 0.46));
}
applySizes();
dragHandle("gutter-v", "x");
dragHandle("gutter-h", "y");

// ------------------------------------------------------------------ boot
readUrl();
dateIn.value = fromDay(state.date);
if (state.lat != null && state.lon != null) {
  placeMarker(state.lat, state.lon, 8);
  load();
} else {
  renderIntro();
}
