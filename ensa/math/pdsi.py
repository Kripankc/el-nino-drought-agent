import numpy as np

def calculate_palmer_z_index(precip_anomaly_pct: float, temp_anomaly_c: float) -> float:
    """
    Palmer 1965 moisture anomaly index (Z-index).
    Models dry anomaly intensity based on atmospheric forecast departures.
    """
    # Precipitation deficit increases severity (negative anomalies)
    precip_factor = precip_anomaly_pct / 100.0  # e.g., -0.25 for -25% precip
    
    # Temperature increases evaporative demand (PET)
    temp_factor = temp_anomaly_c * 0.15
    
    # Combined water balance departure
    z = (1.5 * precip_factor) - temp_factor
    return float(np.round(z, 2))

def calculate_pdsi_forecast(precip_anomaly_pct: float, temp_anomaly_c: float, antecedent_pdsi: float = 0.0) -> dict:
    """
    Palmer 1965 Drought Severity Index (PDSI) forecasting projection.
    Formula: X_t = 0.897 * X_{t-1} + (Z_t / 3)
    """
    z = calculate_palmer_z_index(precip_anomaly_pct, temp_anomaly_c)
    
    # Accumulate Palmer severity over time step
    pdsi = (0.897 * antecedent_pdsi) + (z / 3.0)
    pdsi = float(np.round(pdsi, 2))
    
    # Assign Alert Class based on scientific Palmer thresholds
    if pdsi < -3.0:
        alert = "Extreme Drought"
        recommendation = "Immediate disaster response required. Direct localized food relief pipelines."
    elif -3.0 <= pdsi < -2.0:
        alert = "Severe Drought"
        recommendation = "Warning issued. Prepare agricultural reservoirs and restrict non-essential water draws."
    elif -2.0 <= pdsi < -1.0:
        alert = "Moderate Stress"
        recommendation = "Drought watch. Increase weekly satellite VCI monitoring on vulnerable smallholder wards."
    else:
        alert = "Normal Conditions"
        recommendation = "Climatological baseline. Standby monitoring active."
        
    return {
        "z_index": z,
        "pdsi": pdsi,
        "alert_level": alert,
        "actionable_recommendation": recommendation
    }

if __name__ == "__main__":
    # Test severe drought projection
    proj = calculate_pdsi_forecast(-35.0, 2.2, -1.5)
    print(f"Palmer Projection: {proj}")
