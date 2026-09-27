import "leaflet/dist/leaflet.css";
import "./styles.css";
import L from "leaflet";
import { Day, fromDay, toDay, todayDay } from "./lib/dates";
import { searchPlace, reversePlace } from "./api/geocode";
import { cropsAt, loadCropParams, loadEnso, LocalCrops, CropParamFile } from "./api/static";
import { era5Daily, lastEra5Day } from "./api/openmeteo";
import { Calendar, seasonForYear } from "./calc/season";
import { EnsoData, episodeMonths, seasonPhase } from "./calc/enso";
import { S } from "./strings";
import { el } from "./ui/dom";
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
  if (p.has("lat") && p.has("lon") && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
    state.lat = lat; state.lon = lon;
  }
  const d = p.get("date");
  if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) state.date = Math.min(toDay(d), todayDay());
  state.crop = p.get("crop");
  state.cmp = p.get("cmp") ? Number(p.get("cmp")) : null;
  state.name = p.get("name");
}

function writeUrl() {
  const p = new URLSearchParams();
  if (state.lat != null && state.lon != null) {
    p.set("lat", state.lat.toFixed(4));
    p.set("lon", state.lon.toFixed(4));
  }
  if (state.name) p.set("name", state.name);
  if (state.date !== todayDay()) p.set("date", fromDay(state.date));
  if (state.crop) p.set("crop", state.crop);
  if (state.cmp) p.set("cmp", String(state.cmp));
  history.replaceState(null, "", `${location.pathname}?${p}`);
}

// ------------------------------------------------------------------ DOM
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const form = $<HTMLFormElement>("controls");
const q = $<HTMLInputElement>("q");
const dateIn = $<HTMLInputElement>("date");
const cropSel = $<HTMLSelectElement>("crop");
const cmpSel = $<HTMLSelectElement>("cmp");
const results = $<HTMLUListElement>("results");
const statusEl = $<HTMLParagraphElement>("status");
const report = $<HTMLElement>("report");

export function setStatus(msg: string, isError = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("error", isError);
}

// ------------------------------------------------------------------ map
const map = L.map("map", { worldCopyJump: true }).setView([15, 20], 2);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);
let marker: L.CircleMarker | null = null;

function placeMarker(lat: number, lon: number, zoom?: number) {
  const t = getComputedStyle(document.documentElement).getPropertyValue("--s-this").trim() || "#2a78d6";
  if (marker) marker.setLatLng([lat, lon]);
  else marker = L.circleMarker([lat, lon], { radius: 8, color: "#ffffff", weight: 2, fillColor: t, fillOpacity: 1 }).addTo(map);
  if (zoom) map.setView([lat, lon], zoom);
}

map.on("click", (e: L.LeafletMouseEvent) => {
  const lon = ((((e.latlng.lng + 180) % 360) + 360) % 360) - 180;
  choose(e.latlng.lat, lon, null);
});

async function choose(lat: number, lon: number, name: string | null) {
  state.lat = lat; state.lon = lon; state.name = name; state.cmp = null;
  placeMarker(lat, lon);
  results.replaceChildren();
  if (!name) {
    reversePlace(lat, lon).then((n) => {
      if (n && state.lat === lat && state.lon === lon) {
        state.name = n; writeUrl();
        const h = document.getElementById("place-name");
        if (h) h.textContent = n;
      }
    });
  }
  await load();
}

// ------------------------------------------------------------------ controls
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = q.value.trim();
  if (!text) return;
  const m = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (m) {
    const lat = Number(m[1]);
    const lon = Number(m[2]);
    if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      placeMarker(lat, lon, 9);
      return choose(lat, lon, null);
    }
  }
  setStatus("Searching…");
  try {
    const places = await searchPlace(text);
    results.replaceChildren();
    if (!places.length) { setStatus("No place found. Try a larger town nearby or click the map."); return; }
    setStatus("Pick a result.");
    for (const p of places) {
      const b = el("button", { type: "button" }, p.name);
      b.addEventListener("click", () => { placeMarker(p.lat, p.lon, 9); choose(p.lat, p.lon, p.name.split(",").slice(0, 3).join(",")); });
      results.append(el("li", {}, b));
    }
  } catch (err) {
    setStatus(String((err as Error).message), true);
  }
});

dateIn.max = fromDay(todayDay());
dateIn.addEventListener("change", () => {
  if (!dateIn.value) return;
  state.date = Math.min(toDay(dateIn.value), todayDay());
  if (state.lat != null) load();
});
cropSel.addEventListener("change", () => { state.crop = cropSel.value; state.cmp = null; load(); });
cmpSel.addEventListener("change", () => { state.cmp = cmpSel.value ? Number(cmpSel.value) : null; load(); });

// ------------------------------------------------------------------ crop menu
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
    const sys = k.endsWith("_ir") ? "irrigated" : "rainfed";
    const ha = areaOf(code);
    const share = local.totalHa > 0 && ha > 0 ? ` · ${Math.round((100 * ha) / local.totalHa)}% of area` : "";
    cropSel.append(el("option", { value: k }, `${params.ggcmi_labels[code] ?? code} (${sys})${share}`));
  }
  cropSel.disabled = false;
  const pick = state.crop && keys.includes(state.crop) ? state.crop : keys[0];
  cropSel.value = pick;
  return pick;
}

function fillCmpMenu(cal: Calendar, enso: EnsoData | null, excludeYear: number | null) {
  cmpSel.replaceChildren(el("option", { value: "" }, "None"));
  const lastComplete = (() => {
    let y = new Date().getUTCFullYear();
    while (seasonForYear(cal, y).harvest > lastEra5Day()) y--;
    return y;
  })();
  const years: number[] = [];
  for (let y = lastComplete; y >= 1950; y--) if (y !== excludeYear) years.push(y);
  const label = (y: number) => {
    const s = seasonForYear(cal, y);
    return s.year === new Date(s.harvest * 86_400_000).getUTCFullYear() ? String(y) : `${y}–${String(y + 1).slice(2)}`;
  };
  if (enso) {
    const months = episodeMonths(enso);
    const nino = years.filter((y) => seasonPhase(months, seasonForYear(cal, y)) === "El Nino");
    const og1 = el("optgroup", { label: "El Niño seasons" });
    nino.forEach((y) => og1.append(el("option", { value: String(y) }, label(y))));
    const og2 = el("optgroup", { label: "All seasons" });
    years.forEach((y) => og2.append(el("option", { value: String(y) }, label(y))));
    cmpSel.append(og1, og2);
    if (state.cmp) cmpSel.value = String(state.cmp);
  } else {
    years.forEach((y) => cmpSel.append(el("option", { value: String(y) }, label(y))));
    if (state.cmp) cmpSel.value = String(state.cmp);
  }
  cmpSel.disabled = false;
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
      cropsAt(lat, lon).catch((e) => { console.error(e); return null; }),
    ]);
    if (!alive()) return;
    const localCrops: LocalCrops = local ?? { crops: [], totalHa: 0, cellKm2: 0, calendars: {} };
    const cropKey = fillCropMenu(localCrops, params);
    state.crop = cropKey;
    writeUrl();

    setStatus(S.status.clim);
    const clim = await era5Daily(lat, lon, toDay("1991-01-01"), toDay("2020-12-31"),
      ["precip", "tmax", "tmin", "et0", "rh", "sm"], (m) => alive() && setStatus(m));
    if (!alive()) return;

    const cal: Calendar | null = cropKey
      ? { plantDoy: localCrops.calendars[cropKey][0], maturityDoy: localCrops.calendars[cropKey][1] }
      : null;
    if (cal) fillCmpMenu(cal, enso, null);
    else { cmpSel.replaceChildren(el("option", { value: "" }, "None")); cmpSel.disabled = true; }

    await renderReport({
      root: report, state, params, enso, local: localCrops, cropsLoaded: local != null,
      cropKey, cal, clim: clim.data, grid: clim.grid, alive, setStatus,
    });
    if (!alive()) return;
    setStatus(S.status.done);
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
  setStatus(S.status.idle);
}
