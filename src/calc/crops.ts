// Which crop calendars to offer at a place, and which one to show first.
import { Day } from "../lib/dates";
import { seasonStatus } from "./season";

/** A crop counts as grown here when it has at least this share of harvested area. */
export const MIN_SHARE = 0.02;

export interface CropLike { ha: number; share: number; ggcmi: string[] }
export interface CropChoice { key: string; code: string; share: number; inSeason: boolean; daysToSowing: number | null }

/**
 * Calendars (GGCMI keys such as "mai_rf") for crops that CROPGRIDS maps in the
 * cell, largest harvested area first, rainfed before irrigated. The default is
 * the largest crop in its growing season on `date`; if none is, the largest
 * crop (at least 10% of area) sown next, else the largest crop.
 */
export function cropChoices(crops: CropLike[], calendars: Record<string, [number, number]>, date: Day): { options: CropChoice[]; pick: string | null } {
  const grown = crops.filter((c) => c.share >= MIN_SHARE);
  const options: CropChoice[] = [];
  for (const [key, [plantDoy, maturityDoy]] of Object.entries(calendars)) {
    const code = key.slice(0, 3);
    const crop = grown.find((c) => c.ggcmi.includes(code));
    if (!crop) continue;
    const st = seasonStatus({ plantDoy, maturityDoy }, date);
    options.push({ key, code, share: crop.share, inSeason: st.kind === "in", daysToSowing: st.kind === "in" ? null : st.next.plant - date });
  }
  options.sort((a, b) => b.share - a.share || a.code.localeCompare(b.code) || (a.key.endsWith("_rf") ? -1 : 1));
  const inSeason = options.find((o) => o.inSeason);
  const next = options.filter((o) => o.share >= 0.1 && o.daysToSowing != null).sort((a, b) => a.daysToSowing! - b.daysToSowing!)[0];
  return { options, pick: (inSeason ?? next ?? options[0])?.key ?? null };
}
