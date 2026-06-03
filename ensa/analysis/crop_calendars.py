"""
Crop calendars by region.

Sources (validated June 2026):
  - FAO Crop Calendar  https://cropcalendar.apps.fao.org/
  - FAO Irrigated Crop Calendars https://www.fao.org/aquastat/en/data-analysis/irrig-water-use/irrigated-crop-calendars/
  - FAO Crop Water Requirements (Doorenbos & Pruitt, FAO ID 24/33/56)
  - USDA IPAD Crop Calendars https://ipad.fas.usda.gov/ogamaps/cropcalendar.aspx
  - IRRI Rice Knowledge Bank http://knowledgebank.irri.org/

Each crop entry:
  start, end            - first and last month of the active season (wrap-around supported)
  daily_demand_mm       - average FAO crop water need (ETc) during active season, mm/day
  optimal_temp          - (min, max) C for healthy growth
  stages                - {month: human-readable stage} for all 12 months
                          stage strings containing "Critical" flag pollination/grain-fill windows
"""

# Reusable stage blocks to keep the dict compact and consistent
_FALLOW = "Fallow"
_DORMANT = "Dormant"

CROP_CALENDARS = {

    # ===================================================================
    # NORTH AMERICA  -- US Corn Belt + Canadian Prairies
    # ===================================================================
    "North America": {
        # USDA: maize plant Apr-May, harvest Sep-Oct, full season ~150 days
        "Maize": {
            "start": 4, "end": 10, "daily_demand_mm": 5.5, "optimal_temp": (18, 28),
            "stages": {
                4: "Planting", 5: "Emergence", 6: "Vegetative",
                7: "Tasseling & Silking (Critical)", 8: "Grain Fill (Critical)",
                9: "Maturity", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        # USDA: soybean plant May-Jun, harvest Sep-Oct, full season ~140 days
        "Soybean": {
            "start": 5, "end": 10, "daily_demand_mm": 4.5, "optimal_temp": (20, 30),
            "stages": {
                5: "Planting", 6: "Vegetative",
                7: "Flowering (Critical)", 8: "Pod Fill (Critical)",
                9: "Maturation", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        # FAO: spring wheat plant Apr-Jun, harvest Sep-mid-Nov, 100-130 days
        "Spring Wheat": {
            "start": 4, "end": 9, "daily_demand_mm": 4.5, "optimal_temp": (15, 25),
            "stages": {
                4: "Planting", 5: "Tillering", 6: "Jointing",
                7: "Heading & Flowering (Critical)", 8: "Grain Fill (Critical)",
                9: "Harvesting",
                10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        # USDA: winter wheat plant Sep-Oct, harvest Jun-Jul
        "Winter Wheat": {
            "start": 9, "end": 7, "daily_demand_mm": 4.0, "optimal_temp": (8, 22),
            "stages": {
                9: "Planting", 10: "Germination", 11: "Tillering",
                12: _DORMANT, 1: _DORMANT, 2: "Greenup", 3: "Jointing",
                4: "Heading", 5: "Flowering (Critical)", 6: "Grain Fill (Critical)",
                7: "Harvesting", 8: _FALLOW,
            },
        },
    },

    # ===================================================================
    # SOUTH AMERICA  -- Brazil, Argentina
    # ===================================================================
    "South America": {
        # Soy is the dominant summer crop; plant Oct-Dec, harvest Feb-Apr
        "Soybean": {
            "start": 10, "end": 4, "daily_demand_mm": 5.0, "optimal_temp": (22, 32),
            "stages": {
                10: "Planting", 11: "Emergence", 12: "Vegetative",
                1: "Flowering (Critical)", 2: "Pod Fill (Critical)",
                3: "Maturation", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW,
            },
        },
        # Brazil safrinha + main season; treat as summer maize
        "Maize": {
            "start": 9, "end": 4, "daily_demand_mm": 5.5, "optimal_temp": (20, 30),
            "stages": {
                9: "Planting", 10: "Emergence", 11: "Vegetative", 12: "Vegetative",
                1: "Tasseling (Critical)", 2: "Grain Fill (Critical)",
                3: "Maturity", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW,
            },
        },
        # FAO: winter wheat plant May-Jul (Brazil S, Argentina), harvest Nov-Dec
        "Winter Wheat": {
            "start": 5, "end": 12, "daily_demand_mm": 4.0, "optimal_temp": (12, 22),
            "stages": {
                5: "Planting", 6: "Tillering", 7: "Tillering", 8: "Jointing",
                9: "Heading", 10: "Flowering (Critical)", 11: "Grain Fill (Critical)",
                12: "Harvesting",
                1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        # FAO: sugarcane in Brazil; planting Sep-Nov, peak vegetative Jan-Mar, harvest May-Nov
        "Sugarcane": {
            "start": 1, "end": 12, "daily_demand_mm": 6.5, "optimal_temp": (24, 32),
            "stages": {
                1: "Grand Growth (Critical)", 2: "Grand Growth (Critical)",
                3: "Maturation", 4: "Harvesting", 5: "Harvesting",
                6: "Harvesting", 7: "Harvesting", 8: "Harvesting",
                9: "Planting / Ratoon", 10: "Germination", 11: "Tillering", 12: "Grand Growth",
            },
        },
        # Coffee Arabica  -- Brazil cycle
        "Coffee": {
            "start": 1, "end": 12, "daily_demand_mm": 4.5, "optimal_temp": (18, 24),
            "stages": {
                1: "Bean Expansion", 2: "Flowering (Critical)", 3: "Fruit Set",
                4: "Fruit Development", 5: "Fruit Development (Critical)",
                6: "Ripening", 7: "Harvesting", 8: "Harvesting",
                9: "Post-Harvest Rest", 10: "Vegetative", 11: "Vegetative",
                12: "Pre-flowering",
            },
        },
    },

    # ===================================================================
    # ASIA  -- South Asia + East Asia
    # ===================================================================
    "Nepal": {
        # IRRI: monsoon rice nursery Jun, transplant Jul, harvest Oct-Nov
        "Rice": {
            "start": 6, "end": 11, "daily_demand_mm": 6.0, "optimal_temp": (22, 30),
            "stages": {
                6: "Nursery", 7: "Transplanting", 8: "Tillering",
                9: "Panicle Initiation (Critical)", 10: "Flowering (Critical)",
                11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
        # Rabi wheat Nov-Apr  (Terai + Hills)
        "Wheat": {
            "start": 11, "end": 4, "daily_demand_mm": 4.0, "optimal_temp": (10, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering",
                2: "Jointing", 3: "Heading & Flowering (Critical)", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Maize": {
            "start": 3, "end": 8, "daily_demand_mm": 4.5, "optimal_temp": (18, 28),
            "stages": {
                3: "Planting", 4: "Emergence", 5: "Vegetative",
                6: "Tasseling (Critical)", 7: "Grain Fill (Critical)", 8: "Harvesting",
                9: _FALLOW, 10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW,
            },
        },
        "Millet": {
            "start": 6, "end": 10, "daily_demand_mm": 3.5, "optimal_temp": (20, 30),
            "stages": {
                6: "Planting", 7: "Vegetative", 8: "Flowering (Critical)",
                9: "Grain Filling", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
    },

    "India": {
        # Kharif rice  -- nursery June, transplant Jul, harvest Oct-Nov
        "Rice": {
            "start": 6, "end": 11, "daily_demand_mm": 7.5, "optimal_temp": (25, 33),
            "stages": {
                6: "Nursery & Transplanting", 7: "Tillering",
                8: "Panicle Initiation (Critical)", 9: "Flowering (Critical)",
                10: "Grain Filling", 11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
        # Rabi wheat
        "Wheat": {
            "start": 11, "end": 4, "daily_demand_mm": 4.2, "optimal_temp": (12, 22),
            "stages": {
                11: "Sowing", 12: "Crown Root Initiation", 1: "Tillering",
                2: "Jointing", 3: "Heading & Flowering (Critical)", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        # FAO: India cotton plant Mar-Jul, harvest Sep-Dec. Centre on May plant.
        "Cotton": {
            "start": 5, "end": 12, "daily_demand_mm": 5.5, "optimal_temp": (25, 35),
            "stages": {
                5: "Sowing", 6: "Seedling", 7: "Squaring",
                8: "Flowering (Critical)", 9: "Boll Development (Critical)",
                10: "Boll Opening", 11: "Picking", 12: "Harvesting",
                1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Sugarcane": {
            "start": 2, "end": 1, "daily_demand_mm": 6.0, "optimal_temp": (24, 32),
            "stages": {
                2: "Planting", 3: "Germination", 4: "Tillering",
                5: "Grand Growth", 6: "Grand Growth", 7: "Grand Growth (Critical)",
                8: "Grand Growth (Critical)", 9: "Maturation", 10: "Maturation",
                11: "Harvesting", 12: "Harvesting", 1: "Harvesting",
            },
        },
        "Groundnut": {
            "start": 6, "end": 10, "daily_demand_mm": 4.0, "optimal_temp": (25, 35),
            "stages": {
                6: "Sowing", 7: "Vegetative",
                8: "Flowering & Pegging (Critical)", 9: "Pod Development (Critical)",
                10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
    },

    "Pakistan": {
        "Cotton": {
            "start": 5, "end": 12, "daily_demand_mm": 5.5, "optimal_temp": (26, 36),
            "stages": {
                5: "Sowing", 6: "Seedling", 7: "Squaring",
                8: "Flowering (Critical)", 9: "Boll Development (Critical)",
                10: "Boll Opening", 11: "Picking", 12: "Harvesting",
                1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Wheat": {
            "start": 11, "end": 4, "daily_demand_mm": 4.0, "optimal_temp": (10, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering",
                2: "Jointing", 3: "Heading & Flowering (Critical)", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Rice": {  # Basmati
            "start": 6, "end": 10, "daily_demand_mm": 7.0, "optimal_temp": (24, 32),
            "stages": {
                6: "Nursery", 7: "Transplanting", 8: "Tillering",
                9: "Panicle Initiation (Critical)", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
        "Sugarcane": {
            "start": 3, "end": 2, "daily_demand_mm": 5.5, "optimal_temp": (22, 32),
            "stages": {
                3: "Planting", 4: "Germination", 5: "Tillering",
                6: "Grand Growth", 7: "Grand Growth (Critical)", 8: "Grand Growth (Critical)",
                9: "Maturation", 10: "Maturation", 11: "Harvesting",
                12: "Harvesting", 1: "Harvesting", 2: "Harvesting",
            },
        },
    },

    "Bangladesh": {
        # Aman rice  -- wet season, transplant Jul, harvest Nov
        "Rice (Aman, Wet Season)": {
            "start": 6, "end": 11, "daily_demand_mm": 7.0, "optimal_temp": (25, 33),
            "stages": {
                6: "Nursery", 7: "Transplanting", 8: "Vegetative",
                9: "Panicle Initiation (Critical)", 10: "Flowering (Critical)",
                11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
        # Boro rice  -- dry season, transplant Jan, harvest Apr-May
        "Rice (Boro, Dry Season)": {
            "start": 12, "end": 5, "daily_demand_mm": 8.0, "optimal_temp": (20, 30),
            "stages": {
                12: "Nursery", 1: "Transplanting", 2: "Vegetative",
                3: "Panicle Initiation (Critical)", 4: "Flowering (Critical)",
                5: "Harvesting",
                6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW, 11: _FALLOW,
            },
        },
        "Wheat": {
            "start": 11, "end": 4, "daily_demand_mm": 3.8, "optimal_temp": (12, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering",
                2: "Jointing", 3: "Heading & Flowering (Critical)", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Jute": {
            "start": 3, "end": 8, "daily_demand_mm": 5.0, "optimal_temp": (24, 35),
            "stages": {
                3: "Sowing", 4: "Seedling", 5: "Vegetative", 6: "Vegetative",
                7: "Flowering", 8: "Harvesting",
                9: _FALLOW, 10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW,
            },
        },
    },

    "Myanmar": {
        "Rice": {
            "start": 5, "end": 10, "daily_demand_mm": 7.0, "optimal_temp": (24, 32),
            "stages": {
                5: "Nursery", 6: "Transplanting", 7: "Tillering",
                8: "Panicle Initiation (Critical)", 9: "Flowering (Critical)",
                10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Sesame": {
            "start": 3, "end": 7, "daily_demand_mm": 3.8, "optimal_temp": (26, 35),
            "stages": {
                3: "Sowing", 4: "Seedling", 5: "Vegetative",
                6: "Flowering (Critical)", 7: "Harvesting",
                8: _FALLOW, 9: _FALLOW, 10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW,
            },
        },
    },

    "Southeast Asia": {
        "Rice": {
            "start": 5, "end": 11, "daily_demand_mm": 7.0, "optimal_temp": (24, 33),
            "stages": {
                5: "Nursery", 6: "Transplanting", 7: "Vegetative", 8: "Vegetative",
                9: "Flowering (Critical)", 10: "Grain Filling", 11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Cassava": {
            "start": 3, "end": 12, "daily_demand_mm": 4.0, "optimal_temp": (25, 35),
            "stages": {
                3: "Planting", 4: "Establishment", 5: "Vegetative",
                6: "Vegetative (Critical)", 7: "Tuber Bulking (Critical)",
                8: "Tuber Bulking", 9: "Maturation", 10: "Maturation",
                11: "Harvest Ready", 12: "Harvesting",
                1: _FALLOW, 2: _FALLOW,
            },
        },
        "Sugarcane": {
            "start": 1, "end": 12, "daily_demand_mm": 6.0, "optimal_temp": (24, 33),
            "stages": {
                1: "Grand Growth", 2: "Grand Growth", 3: "Grand Growth (Critical)",
                4: "Maturation", 5: "Harvesting", 6: "Planting / Ratoon",
                7: "Germination", 8: "Tillering", 9: "Grand Growth",
                10: "Grand Growth (Critical)", 11: "Maturation", 12: "Harvesting",
            },
        },
    },

    "China": {
        # Double-crop rice (early) -- transplant Apr, harvest Jul
        "Rice": {
            "start": 4, "end": 8, "daily_demand_mm": 6.5, "optimal_temp": (23, 30),
            "stages": {
                4: "Transplanting", 5: "Tillering",
                6: "Panicle Initiation (Critical)", 7: "Flowering (Critical)",
                8: "Harvesting",
                9: _FALLOW, 10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Wheat": {  # winter wheat
            "start": 10, "end": 6, "daily_demand_mm": 4.5, "optimal_temp": (10, 22),
            "stages": {
                10: "Sowing", 11: "Germination",
                12: _DORMANT, 1: _DORMANT, 2: "Returning Green", 3: "Jointing",
                4: "Heading", 5: "Flowering (Critical)", 6: "Harvesting",
                7: _FALLOW, 8: _FALLOW, 9: _FALLOW,
            },
        },
        "Maize": {
            "start": 6, "end": 9, "daily_demand_mm": 5.0, "optimal_temp": (22, 30),
            "stages": {
                6: "Planting", 7: "Vegetative",
                8: "Tasseling & Silking (Critical)", 9: "Grain Fill & Harvest",
                10: _FALLOW, 11: _FALLOW, 12: _FALLOW,
                1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
        # USDA: China cotton Apr-Jun plant, harvest Sep-Oct
        "Cotton": {
            "start": 4, "end": 10, "daily_demand_mm": 5.5, "optimal_temp": (24, 33),
            "stages": {
                4: "Sowing", 5: "Seedling", 6: "Squaring",
                7: "Flowering (Critical)", 8: "Boll Development (Critical)",
                9: "Boll Opening", 10: "Picking",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
    },

    # ===================================================================
    # AFRICA
    # ===================================================================
    "East Africa": {
        "Maize (Long Rains)": {
            "start": 3, "end": 9, "daily_demand_mm": 4.8, "optimal_temp": (18, 26),
            "stages": {
                3: "Planting", 4: "Vegetative", 5: "Vegetative",
                6: "Tasseling & Silking (Critical)", 7: "Grain Filling",
                8: "Maturity", 9: "Harvesting",
                10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW,
            },
        },
        "Maize (Short Rains)": {
            "start": 10, "end": 2, "daily_demand_mm": 4.8, "optimal_temp": (18, 26),
            "stages": {
                10: "Planting", 11: "Vegetative", 12: "Tasseling (Critical)",
                1: "Grain Filling", 2: "Harvesting",
                3: _FALLOW, 4: _FALLOW, 5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW,
            },
        },
        "Sorghum": {
            "start": 4, "end": 10, "daily_demand_mm": 3.5, "optimal_temp": (22, 32),
            "stages": {
                4: "Planting", 5: "Vegetative", 6: "Vegetative",
                7: "Flowering (Critical)", 8: "Grain Filling",
                9: "Maturity", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Tea": {
            "start": 1, "end": 12, "daily_demand_mm": 4.5, "optimal_temp": (15, 25),
            "stages": {
                1: _DORMANT, 2: "Bud Burst",
                3: "Flush (Critical)", 4: "Flush (Critical)", 5: "Flush (Critical)",
                6: "Flush", 7: "Flush", 8: "Flush (Critical)",
                9: "Flush", 10: "Flush", 11: "Semi-dormant", 12: _DORMANT,
            },
        },
        "Coffee": {
            "start": 3, "end": 11, "daily_demand_mm": 4.0, "optimal_temp": (15, 24),
            "stages": {
                3: "Vegetative", 4: "Vegetative",
                5: "Flowering (Critical)", 6: "Fruit Set",
                7: "Fruit Development (Critical)", 8: "Fruit Development",
                9: "Ripening", 10: "Harvesting", 11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW,
            },
        },
    },

    "West Africa": {
        # FAO/IPAD: Sahel maize sow Apr-May (south) or Jun (north), harvest Sep-Oct
        "Maize": {
            "start": 5, "end": 10, "daily_demand_mm": 4.5, "optimal_temp": (22, 32),
            "stages": {
                5: "Sowing & Emergence", 6: "Vegetative", 7: "Vegetative",
                8: "Tasseling & Silking (Critical)", 9: "Grain Filling",
                10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Millet": {
            "start": 5, "end": 10, "daily_demand_mm": 3.8, "optimal_temp": (25, 35),
            "stages": {
                5: "Planting", 6: "Vegetative", 7: "Vegetative",
                8: "Flowering (Critical)", 9: "Grain Filling", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Sorghum": {
            "start": 5, "end": 10, "daily_demand_mm": 4.0, "optimal_temp": (25, 35),
            "stages": {
                5: "Planting", 6: "Vegetative", 7: "Vegetative",
                8: "Flowering (Critical)", 9: "Grain Filling", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Groundnut": {
            "start": 5, "end": 10, "daily_demand_mm": 3.5, "optimal_temp": (25, 35),
            "stages": {
                5: "Sowing", 6: "Vegetative",
                7: "Flowering & Pegging (Critical)", 8: "Pod Development (Critical)",
                9: "Maturation", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Cowpea": {
            "start": 6, "end": 10, "daily_demand_mm": 3.0, "optimal_temp": (25, 35),
            "stages": {
                6: "Planting", 7: "Vegetative",
                8: "Flowering (Critical)", 9: "Pod Filling", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW, 5: _FALLOW,
            },
        },
    },

    "Southern Africa": {
        # FAO/SADC: maize plant Nov-Dec, peak flowering Feb-Mar, harvest May-Jul
        "Maize": {
            "start": 11, "end": 7, "daily_demand_mm": 5.0, "optimal_temp": (20, 28),
            "stages": {
                11: "Planting", 12: "Emergence",
                1: "Vegetative", 2: "Vegetative",
                3: "Flowering & Tasseling (Critical)", 4: "Grain Fill (Critical)",
                5: "Maturity", 6: "Harvesting", 7: "Harvesting",
                8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Sorghum / Millet": {
            "start": 12, "end": 6, "daily_demand_mm": 3.8, "optimal_temp": (24, 32),
            "stages": {
                12: "Planting", 1: "Vegetative", 2: "Vegetative", 3: "Vegetative",
                4: "Flowering (Critical)", 5: "Maturity", 6: "Harvesting",
                7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW, 11: _FALLOW,
            },
        },
        "Groundnut": {
            "start": 11, "end": 4, "daily_demand_mm": 4.0, "optimal_temp": (22, 32),
            "stages": {
                11: "Sowing", 12: "Vegetative",
                1: "Flowering & Pegging (Critical)", 2: "Pod Development (Critical)",
                3: "Maturation", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Soybean": {
            "start": 11, "end": 4, "daily_demand_mm": 4.5, "optimal_temp": (20, 30),
            "stages": {
                11: "Planting", 12: "Emergence", 1: "Vegetative",
                2: "Flowering (Critical)", 3: "Pod Fill (Critical)", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Cassava": {
            "start": 11, "end": 10, "daily_demand_mm": 3.5, "optimal_temp": (22, 32),
            "stages": {
                11: "Planting", 12: "Establishment (Critical)",
                1: "Vegetative (Critical)", 2: "Tuber Initiation",
                3: "Tuber Bulking (Critical)", 4: "Tuber Bulking",
                5: "Maturation", 6: "Maturation", 7: "Maturation", 8: "Maturation",
                9: "Harvest Ready", 10: "Harvesting",
            },
        },
        "Tobacco": {
            "start": 10, "end": 3, "daily_demand_mm": 4.5, "optimal_temp": (20, 28),
            "stages": {
                10: "Nursery", 11: "Transplanting", 12: "Establishment",
                1: "Grand Growth (Critical)", 2: "Maturation", 3: "Harvesting",
                4: _FALLOW, 5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW,
            },
        },
    },

    # ===================================================================
    # OCEANIA
    # ===================================================================
    "Australia": {
        "Wheat": {  # winter wheat
            "start": 5, "end": 11, "daily_demand_mm": 3.8, "optimal_temp": (10, 20),
            "stages": {
                5: "Sowing & Emergence", 6: "Tillering", 7: "Jointing",
                8: "Booting", 9: "Heading & Flowering (Critical)",
                10: "Grain Fill", 11: "Harvesting",
                12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Barley": {
            "start": 5, "end": 10, "daily_demand_mm": 3.6, "optimal_temp": (12, 22),
            "stages": {
                5: "Sowing & Emergence", 6: "Tillering", 7: "Jointing",
                8: "Flowering (Critical)", 9: "Grain Filling", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW, 4: _FALLOW,
            },
        },
        "Canola": {
            "start": 4, "end": 10, "daily_demand_mm": 3.5, "optimal_temp": (10, 22),
            "stages": {
                4: "Sowing", 5: "Emergence", 6: "Vegetative",
                7: "Flowering (Critical)", 8: "Pod Fill (Critical)",
                9: "Maturation", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Sorghum": {  # summer sorghum
            "start": 10, "end": 4, "daily_demand_mm": 4.0, "optimal_temp": (22, 35),
            "stages": {
                10: "Planting", 11: "Vegetative", 12: "Vegetative",
                1: "Flowering (Critical)", 2: "Grain Fill", 3: "Maturity", 4: "Harvesting",
                5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW,
            },
        },
    },

    # ===================================================================
    # OTHER REGIONS
    # ===================================================================
    "North Africa": {
        "Wheat": {  # winter wheat / barley dominate
            "start": 11, "end": 6, "daily_demand_mm": 4.0, "optimal_temp": (10, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering", 2: "Jointing",
                3: "Heading", 4: "Flowering (Critical)",
                5: "Grain Fill (Critical)", 6: "Harvesting",
                7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Barley": {
            "start": 11, "end": 5, "daily_demand_mm": 3.5, "optimal_temp": (8, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering", 2: "Jointing",
                3: "Heading", 4: "Flowering (Critical)", 5: "Harvesting",
                6: _FALLOW, 7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
        "Olive": {
            "start": 1, "end": 12, "daily_demand_mm": 2.0, "optimal_temp": (10, 30),
            "stages": {
                1: _DORMANT, 2: "Bud Swell", 3: "Flowering (Critical)",
                4: "Fruit Set", 5: "Fruit Growth", 6: "Pit Hardening",
                7: "Fruit Development (Critical)", 8: "Ripening",
                9: "Ripening", 10: "Harvesting", 11: "Harvesting", 12: _DORMANT,
            },
        },
    },

    "Central Asia": {
        "Cotton": {
            "start": 4, "end": 10, "daily_demand_mm": 5.5, "optimal_temp": (25, 35),
            "stages": {
                4: "Sowing", 5: "Emergence", 6: "Squaring",
                7: "Flowering (Critical)", 8: "Boll Development (Critical)",
                9: "Boll Opening", 10: "Picking",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Wheat": {  # winter wheat
            "start": 10, "end": 7, "daily_demand_mm": 4.0, "optimal_temp": (8, 20),
            "stages": {
                10: "Sowing", 11: "Germination",
                12: _DORMANT, 1: _DORMANT, 2: "Returning Green", 3: "Jointing",
                4: "Heading", 5: "Flowering (Critical)", 6: "Grain Fill", 7: "Harvesting",
                8: _FALLOW, 9: _FALLOW,
            },
        },
    },

    "Europe": {
        "Wheat": {  # winter wheat
            "start": 10, "end": 7, "daily_demand_mm": 3.5, "optimal_temp": (8, 20),
            "stages": {
                10: "Sowing", 11: "Germination",
                12: _DORMANT, 1: _DORMANT, 2: "Returning Green", 3: "Jointing",
                4: "Heading", 5: "Flowering (Critical)", 6: "Grain Fill", 7: "Harvesting",
                8: _FALLOW, 9: _FALLOW,
            },
        },
        "Sunflower": {
            "start": 4, "end": 9, "daily_demand_mm": 4.0, "optimal_temp": (18, 28),
            "stages": {
                4: "Sowing", 5: "Emergence", 6: "Vegetative",
                7: "Flowering (Critical)", 8: "Seed Fill (Critical)", 9: "Harvesting",
                10: _FALLOW, 11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Maize": {  # summer maize
            "start": 4, "end": 10, "daily_demand_mm": 4.5, "optimal_temp": (18, 28),
            "stages": {
                4: "Sowing", 5: "Emergence", 6: "Vegetative",
                7: "Tasseling (Critical)", 8: "Grain Fill (Critical)",
                9: "Maturation", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
    },

    "Sri Lanka": {
        "Rice (Maha, Main)": {
            "start": 9, "end": 3, "daily_demand_mm": 7.0, "optimal_temp": (24, 32),
            "stages": {
                9: "Nursery", 10: "Transplanting", 11: "Vegetative",
                12: "Panicle Initiation (Critical)", 1: "Flowering (Critical)",
                2: "Grain Fill", 3: "Harvesting",
                4: _FALLOW, 5: _FALLOW, 6: _FALLOW, 7: _FALLOW, 8: _FALLOW,
            },
        },
        "Rice (Yala, Secondary)": {
            "start": 4, "end": 8, "daily_demand_mm": 7.0, "optimal_temp": (26, 34),
            "stages": {
                4: "Nursery", 5: "Transplanting", 6: "Vegetative",
                7: "Flowering (Critical)", 8: "Harvesting",
                9: _FALLOW, 10: _FALLOW, 11: _FALLOW, 12: _FALLOW,
                1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Tea": {
            "start": 1, "end": 12, "daily_demand_mm": 4.5, "optimal_temp": (16, 24),
            "stages": {
                1: _DORMANT, 2: "Bud Burst",
                3: "Flush (Critical)", 4: "Flush (Critical)", 5: "Flush",
                6: "Flush", 7: "Flush (Critical)", 8: "Flush (Critical)",
                9: "Flush", 10: "Flush", 11: "Semi-dormant", 12: _DORMANT,
            },
        },
    },

    "Global": {
        "Maize": {
            "start": 4, "end": 10, "daily_demand_mm": 5.0, "optimal_temp": (18, 28),
            "stages": {
                4: "Planting", 5: "Emergence", 6: "Vegetative",
                7: "Tasseling (Critical)", 8: "Grain Fill", 9: "Maturation", 10: "Harvesting",
                11: _FALLOW, 12: _FALLOW, 1: _FALLOW, 2: _FALLOW, 3: _FALLOW,
            },
        },
        "Wheat": {
            "start": 11, "end": 6, "daily_demand_mm": 4.0, "optimal_temp": (10, 22),
            "stages": {
                11: "Sowing", 12: "Germination", 1: "Tillering",
                2: "Jointing", 3: "Heading", 4: "Flowering (Critical)",
                5: "Grain Fill (Critical)", 6: "Harvesting",
                7: _FALLOW, 8: _FALLOW, 9: _FALLOW, 10: _FALLOW,
            },
        },
    },
}
