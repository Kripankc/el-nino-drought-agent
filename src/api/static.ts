// Loaders for the pre-built data files under public/data (see pipeline/).
import type { CropParams } from "../calc/season";
import type { EnsoData } from "../calc/enso";

const cache = new Map<string, Promise<any>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path)!;
}

export interface CropIndex {
  area_res: number;
  cal_res: number;
  tile_deg: number;
  min_cell_ha: number;
  crops: { id: number; name: string; param: string | null; ggcmi: string[]; global_ha: number }[];
  sources: { area: string; calendar: string };
}

export interface CropParamFile {
  ggcmi_to_param: Record<string, string>;
  ggcmi_labels: Record<string, string>;
  params: Record<string, CropParams>;
  references: Record<string, string>;
}

interface Tile { a: Record<string, [number, [number, number][]]>; c: Record<string, Record<string, [number, number]>> }

export const loadCropIndex = () => load<CropIndex>("crops/index.json");
export const loadCropParams = () => load<CropParamFile>("crop_params.json");
export const loadEnso = () => load<EnsoData>("enso.json");

function cellKey(lat: number, lon: number, res: number): { i: number; j: number } {
  const i = Math.min(Math.floor((lat + 90) / res), Math.round(180 / res) - 1);
  const j = Math.min(Math.floor((((lon + 180) % 360) + 360) % 360 / res), Math.round(360 / res) - 1);
  return { i, j };
}

async function tileFor(lat: number, lon: number, res: number, tileDeg: number): Promise<Tile | null> {
  const { i, j } = cellKey(lat, lon, res);
  const per = Math.round(tileDeg / res);
  try {
    return await load<Tile>(`crops/${Math.floor(i / per)}_${Math.floor(j / per)}.json`);
  } catch {
    return null; // no tile = no cropland and no calendar in that 10x10 deg block
  }
}

export interface CropHere { id: number; name: string; ha: number; share: number; param: string | null; ggcmi: string[] }
export interface LocalCrops {
  crops: CropHere[];
  totalHa: number;        // harvested area of all crops in the 0.25 deg cell
  cellKm2: number;        // land+water area of that cell
  calendars: Record<string, [number, number]>; // "mai_rf" -> [plantDoy, maturityDoy]
}

export async function cropsAt(lat: number, lon: number): Promise<LocalCrops> {
  const idx = await loadCropIndex();
  const areaTile = await tileFor(lat, lon, idx.area_res, idx.tile_deg);
  const calTile = await tileFor(lat, lon, idx.cal_res, idx.tile_deg);
  const a = cellKey(lat, lon, idx.area_res);
  const c = cellKey(lat, lon, idx.cal_res);
  const [totalHa, entries] = areaTile?.a[`${a.i}_${a.j}`] ?? [0, []];
  const byId = new Map(idx.crops.map((x) => [x.id, x]));
  return {
    crops: entries.map(([id, ha]) => {
      const m = byId.get(id)!;
      return { id, name: m.name, ha, share: totalHa ? ha / totalHa : 0, param: m.param, ggcmi: m.ggcmi };
    }),
    totalHa,
    cellKm2: (idx.area_res * 111.32) ** 2 * Math.cos((((a.i + 0.5) * idx.area_res - 90) * Math.PI) / 180),
    calendars: calTile?.c[`${c.i}_${c.j}`] ?? {},
  };
}
