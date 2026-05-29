-- Comprehensive Schema for ENSA Edge Node Relational Storage

-- 1. Regional Bounding Box Targets
CREATE TABLE IF NOT EXISTS regional_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_name VARCHAR(100) UNIQUE NOT NULL,
    country VARCHAR(100) NOT NULL,
    crop_type VARCHAR(50) DEFAULT 'Maize',
    bbox_coords VARCHAR(100) NOT NULL, -- Format: "min_lon,min_lat,max_lon,max_lat"
    is_scheduled BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Forecast and Satellite Observation Logs (Integrated Correlation & PDSI)
CREATE TABLE IF NOT EXISTS forecast_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_date DATE NOT NULL,
    target_region VARCHAR(100) NOT NULL,
    raw_spei3 FLOAT NOT NULL,
    observed_vci FLOAT NOT NULL,
    observed_ndwi FLOAT NOT NULL,
    observed_lst FLOAT NOT NULL,
    pearson_r FLOAT,
    precipitation_weight FLOAT,
    vegetation_weight FLOAT,
    soil_moisture_weight FLOAT,
    fusion_type VARCHAR(50), -- e.g., "Correlation-Weighted Fusion" or "Ensemble Fallback"
    projected_pdsi FLOAT,
    confidence_score FLOAT,
    alert_level VARCHAR(30), -- e.g., "Extreme Drought", "Severe Drought", "Moderate Stress", "Normal"
    literature_citations TEXT, -- JSON string of academic citations
    cloud_review_pending BOOLEAN DEFAULT 0,
    ground_truth_pdsi_later FLOAT, -- Commited 30 days later for skill verification
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Self-Correction & Parametric Adjustments Journal (Learned Memory)
CREATE TABLE IF NOT EXISTS self_correction_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_date DATE NOT NULL,
    assessment_period VARCHAR(50) NOT NULL,
    target_district VARCHAR(100) NOT NULL,
    raw_pdsi_forecast FLOAT,
    observed_pdsi FLOAT,
    forecast_rmse FLOAT,
    agent_reasoning TEXT,
    parameter_adjustments TEXT, -- JSON block of weight calibrations
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
