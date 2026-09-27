import { Day, dayFromDoy, ymd } from "../lib/dates";

export interface Calendar {
  plantDoy: number;     // GGCMI planting day of year
  maturityDoy: number;  // GGCMI maturity day of year
}

export interface Season {
  plant: Day;
  harvest: Day;   // maturity day
  length: number; // days, harvest - plant
  year: number;   // calendar year of planting (used to label the season)
}

export function seasonLength(cal: Calendar): number {
  const L = (cal.maturityDoy - cal.plantDoy + 365) % 365;
  return L === 0 ? 365 : L;
}

export function seasonForYear(cal: Calendar, plantYear: number): Season {
  const plant = dayFromDoy(plantYear, cal.plantDoy);
  const length = seasonLength(cal);
  return { plant, harvest: plant + length, length, year: plantYear };
}

export type SeasonStatus =
  | { kind: "in"; season: Season; dayOfSeason: number }
  | { kind: "off"; last: Season; next: Season };

/** Where does `date` fall relative to the crop calendar? */
export function seasonStatus(cal: Calendar, date: Day): SeasonStatus {
  const y = ymd(date).y;
  const cands = [y - 2, y - 1, y, y + 1].map((yy) => seasonForYear(cal, yy));
  const cur = cands.find((s) => date >= s.plant && date <= s.harvest);
  if (cur) return { kind: "in", season: cur, dayOfSeason: date - cur.plant + 1 };
  const last = cands.filter((s) => s.harvest < date).pop()!;
  const next = cands.find((s) => s.plant > date)!;
  return { kind: "off", last, next };
}

// ---------------------------------------------------------------- FAO-56
export interface CropParams {
  kc: [number, number, number] | null;       // ini, mid, end
  stages: [number, number, number, number] | null; // FAO-56 Table 11 day counts
  heat_c: number | null;
  heat_ref: string | null;
  kc_range: string;
  stage_row: string | null;
}

export interface StagePlan {
  bounds: [number, number, number, number]; // cumulative end day (1-based) of ini, dev, mid, late
  names: [string, string, string, string];
}

export const STAGE_NAMES: [string, string, string, string] = [
  "Initial", "Development", "Mid-season", "Late season",
];

/** Scale FAO-56 stage proportions to the local season length. */
export function stagePlan(stages: [number, number, number, number], length: number): StagePlan {
  const total = stages.reduce((a, b) => a + b, 0);
  const b1 = Math.round((stages[0] / total) * length);
  const b2 = b1 + Math.round((stages[1] / total) * length);
  const b3 = b2 + Math.round((stages[2] / total) * length);
  return { bounds: [b1, b2, b3, length], names: STAGE_NAMES };
}

export function stageIndex(plan: StagePlan, dayOfSeason: number): number {
  return plan.bounds.findIndex((b) => dayOfSeason <= b);
}

/**
 * FAO-56 single crop coefficient curve (Allen et al. 1998, Fig. 25):
 * constant Kc_ini, linear rise to Kc_mid over development, constant Kc_mid,
 * linear change to Kc_end over the late season.
 */
export function kcOnDay(kc: [number, number, number], plan: StagePlan, dayOfSeason: number): number {
  const [ini, mid, end] = kc;
  const [b1, b2, b3, b4] = plan.bounds;
  const t = dayOfSeason;
  if (t <= b1) return ini;
  if (t <= b2) return ini + ((t - b1) / Math.max(1, b2 - b1)) * (mid - ini);
  if (t <= b3) return mid;
  return mid + ((t - b3) / Math.max(1, b4 - b3)) * (end - mid);
}

// ------------------------------------------------ Effective rainfall (USDA-SCS)
/**
 * USDA-SCS effective rainfall, monthly form used in FAO CROPWAT.
 * For a partial month of `days` days the monthly formula is applied to the
 * rainfall scaled to a 30.4-day month and scaled back (pro-rata).
 */
export function effectiveRain(pMm: number, days = 30.4): number {
  const f = 30.4 / days;
  const P = pMm * f;
  const peff = P <= 250 ? (P * (125 - 0.2 * P)) / 125 : 125 + 0.1 * P;
  return Math.max(0, peff) / f;
}
