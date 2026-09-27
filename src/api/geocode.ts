// OpenStreetMap Nominatim. Usage policy: max 1 request/second, no bulk use,
// attribution required. Searches run only on submit, never while typing.
const BASE = "https://nominatim.openstreetmap.org";

export interface Place { name: string; lat: number; lon: number }

export async function searchPlace(q: string): Promise<Place[]> {
  const p = new URLSearchParams({ q, format: "jsonv2", limit: "6", "accept-language": "en" });
  const r = await fetch(`${BASE}/search?${p}`);
  if (!r.ok) throw new Error(`Place search failed (${r.status})`);
  const j = (await r.json()) as { display_name: string; lat: string; lon: string }[];
  return j.map((x) => ({ name: x.display_name, lat: Number(x.lat), lon: Number(x.lon) }));
}

export async function reversePlace(lat: number, lon: number): Promise<string | null> {
  const p = new URLSearchParams({ lat: String(lat), lon: String(lon), format: "jsonv2", zoom: "10", "accept-language": "en" });
  try {
    const r = await fetch(`${BASE}/reverse?${p}`);
    if (!r.ok) return null;
    const j = await r.json();
    const a = j.address ?? {};
    const parts = [a.village ?? a.town ?? a.city ?? a.county ?? a.state_district, a.state, a.country].filter(Boolean);
    return parts.length ? parts.join(", ") : (j.display_name ?? null);
  } catch {
    return null;
  }
}
