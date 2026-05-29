import numpy as np
import pandas as pd

def calculate_multi_event_bias(forecast_history: list, observed_history: list) -> float:
    """
    Calculates the average prediction gap (bias) between historical climate model
    forecast predictions and actual satellite ground-truth observations.
    Equation: Bias = 1/N * sum(Forecast_e - Observed_e)
    """
    f = np.array(forecast_history)
    o = np.array(observed_history)
    
    if len(f) == 0 or len(o) == 0:
        return 0.0
        
    return float(np.mean(f - o))

def apply_bias_correction(raw_forecast: float, bias_value: float) -> float:
    """
    Calibrates a raw physical forecast by applying the dynamic bias adjustment factor.
    Equation: Forecast_calibrated = Forecast_raw - Bias
    """
    return float(raw_forecast - bias_value)

def calculate_forecast_skill(raw_forecasts: list, calibrated_forecasts: list, actual_observations: list) -> dict:
    """
    Calculates statistical metrics to verify forecast performance improvement.
    Computes RMSE (Root Mean Squared Error) and MAE (Mean Absolute Error) for both models.
    We target: RMSE(calibrated) < RMSE(raw)
    """
    f_raw = np.array(raw_forecasts)
    f_cal = np.array(calibrated_forecasts)
    act = np.array(actual_observations)
    
    rmse_raw = np.sqrt(np.mean((f_raw - act) ** 2))
    rmse_cal = np.sqrt(np.mean((f_cal - act) ** 2))
    
    mae_raw = np.mean(np.abs(f_raw - act))
    mae_cal = np.mean(np.abs(f_cal - act))
    
    skill_improvement_pct = ((rmse_raw - rmse_cal) / (rmse_raw + 1e-8)) * 100
    
    return {
        "rmse_raw": float(np.round(rmse_raw, 3)),
        "rmse_calibrated": float(np.round(rmse_cal, 3)),
        "mae_raw": float(np.round(mae_raw, 3)),
        "mae_calibrated": float(np.round(mae_cal, 3)),
        "skill_improvement_pct": float(np.round(skill_improvement_pct, 2))
    }

if __name__ == "__main__":
    # Test skill calculations
    raw = [50.0, 52.0, 48.0]
    cal = [42.0, 43.0, 41.0]
    actual = [41.0, 42.0, 40.0]
    
    bias = calculate_multi_event_bias(raw, actual)
    print(f"Computed Historical Bias: {bias}")
    
    skill = calculate_forecast_skill(raw, cal, actual)
    print(f"Skill Metrics: {skill}")
