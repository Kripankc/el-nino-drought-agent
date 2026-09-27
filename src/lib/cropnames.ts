// Readable names for the CROPGRIDS / Monfreda et al. (2008) crop codes.
const EXPLICIT: Record<string, string> = {
  bean: "Beans (dry)", pea: "Peas (dry)", sweetpotato: "Sweet potato", oilpalm: "Oil palm",
  broadbean: "Broad bean", greenbean: "Green bean", greenbroadbean: "Green broad bean",
  greencorn: "Green maize", greenonion: "Green onion", greenpea: "Green pea",
  lemonlime: "Lemon and lime", jutelikefiber: "Jute-like fibres", kapokfiber: "Kapok fibre",
  kapokseed: "Kapok seed", karite: "Shea (karité)", melonseed: "Melon seed", mixedgrain: "Mixed grain",
  mixedgrass: "Mixed grasses", pigeonpea: "Pigeon pea", sourcherry: "Sour cherry", stringbean: "String bean",
  sugarbeet: "Sugar beet", sugarcane: "Sugarcane", canaryseed: "Canary seed", cashewapple: "Cashew apple",
  hempseed: "Hemp seed", kolanut: "Kola nut", rasberry: "Raspberry", brazil: "Brazil nut",
  chilleetc: "Chillies and peppers", aniseetc: "Anise, fennel etc.", cucumberetc: "Cucumbers etc.",
  grapefruitetc: "Grapefruit etc.", melonetc: "Melons etc.", peachetc: "Peaches etc.",
  pumpkinetc: "Pumpkins etc.", tangetc: "Tangerines etc.", vegfor: "Vegetables (forage)",
  fornes: "Other forage crops",
};
const NES: Record<string, string> = {
  berry: "berries", cereal: "cereals", citrus: "citrus fruit", fibre: "fibre crops", fruit: "fruit",
  grass: "grasses", legume: "legumes", nut: "nuts", oilseed: "oilseeds", pulse: "pulses",
  root: "roots and tubers", spice: "spices", stonefruit: "stone fruit", sugar: "sugar crops",
  tropical: "tropical fruit", vegetable: "vegetables",
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function cropName(code: string): string {
  const c = code.toLowerCase().replace(/\s+/g, "");
  if (EXPLICIT[c]) return EXPLICIT[c];
  if (c.endsWith("nes") && NES[c.slice(0, -3)]) return `Other ${NES[c.slice(0, -3)]}`;
  if (c.endsWith("for") && c.length > 3) return `${cap(c.slice(0, -3))} (forage)`;
  return cap(code);
}
