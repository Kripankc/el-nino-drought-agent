// Fixed interface text. Sentences that embed numbers are built next to the
// numbers in sections.ts.
export const S = {
  status: {
    idle: "Search for a place or click the map.",
    crops: "Loading crop map and calendar…",
    clim: "Loading the 1991–2020 normals for this place…",
    season: "Loading ERA5 data for this season…",
    forecast: "Loading forecasts…",
    done: "Done.",
    enso: "Loading rain and temperature for every season since 1950…",
  },
  h: {
    here: "Crops and seasons",
    strip: "Crop season",
    water: "Rain and crop water need",
    temp: "Heat",
    other: "Soil and air",
    fc: "Next 15 days",
    seas: "Next 7 months",
    after: "What happened next",
    enso: "El Niño",
    advice: "What to do",
    limits: "Limits of this page",
  },
  limits: [
    "ERA5 is a global reanalysis on a ~31 km grid. Rainfall in mountains and in areas with scattered thunderstorms can differ a lot from what falls on one field.",
    "Crop areas are circa 2020 and crop calendars are one typical season per 0.5° cell (~50 km). Local sowing dates and varieties differ, especially for past decades.",
    "Crop water need is FAO-56 ETc for a healthy, well-watered crop. It does not include paddy flooding, land preparation or field losses.",
    "Seasonal forecasts give the tendency of the coming months over a wide area. They are often wrong at a single place.",
    "Guidance on this page is general. Always confirm decisions with your local agricultural extension service.",
  ],
};
