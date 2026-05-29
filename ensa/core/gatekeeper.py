import numpy as np
import scipy.stats as stats

def calculate_forecast_confidence(spei_val: float, vci_val: float, cloud_free_fraction: float) -> float:
    """
    Computes a mathematical confidence score (0.0 to 1.0) for an alert prediction.
    Agreement Logic:
    - If atmospheric index (SPEI) and biological index (VCI) agree on the threat direction,
      confidence is high.
    - If they disagree (e.g., SPEI shows severe drought but VCI remains normal/green, 
      indicating heavy local irrigation), confidence is low and requires Cloud agent review.
    """
    spei_risk = clip_to_range(abs(spei_val) / 2.0 if spei_val < 0 else 0.0, 0.0, 1.0)
    vci_risk = clip_to_range((100.0 - vci_val) / 100.0, 0.0, 1.0)
    divergence = abs(spei_risk - vci_risk)
    
    agreement_score = 1.0 - divergence
    confidence = (agreement_score * 0.7) + (cloud_free_fraction * 0.3)
    return float(np.round(clip_to_range(confidence, 0.0, 1.0), 3))

def should_trigger_cloud_review(confidence: float) -> bool:
    """
    Literature-backed threshold: If confidence drops below 0.8,
    we flag it to batch-sync with Cloud LLM (Gemini 1.5 Flash) for calibration.
    """
    return confidence < 0.8

def calculate_pearson_correlation(series_a: list, series_b: list) -> float:
    """
    Computes Pearson correlation coefficient (r) between satellite indices and meteorological indices.
    """
    if len(series_a) < 3 or len(series_b) < 3:
        return 0.0
    r, _ = stats.pearsonr(series_a, series_b)
    return float(np.round(r, 3)) if not np.isnan(r) else 0.0

def derive_dynamic_correlation_weights(r_precip: float, r_veg: float, r_soil: float) -> dict:
    """
    Flowchart Decision Block: Check if Pearson Correlation r > 0.65 threshold.
    - If YES (r > 0.65): Apply correlation-weighted dynamic indicator fusion.
    - If NO (r <= 0.65): Fallback to Ensemble Average (equal weights).
    """
    weights = {}
    r_vals = [abs(r_precip), abs(r_veg), abs(r_soil)]
    max_r = max(r_vals)
    
    if max_r > 0.65:
        # Dynamic Correlation-Weighted Indicator Fusion
        print(f"[Gatekeeper] Strong ground-satellite agreement (r={max_r:.2f} > 0.65). Applying dynamic weighting.")
        total_r = sum(r_vals) + 1e-8
        weights["precipitation"] = round(abs(r_precip) / total_r, 2)
        weights["vegetation"] = round(abs(r_veg) / total_r, 2)
        weights["soil_moisture"] = round(abs(r_soil) / total_r, 2)
        weights["fusion_type"] = "Correlation-Weighted Fusion"
    else:
        # Fallback to Ensemble Average (equal weights)
        print(f"[Gatekeeper] Poor agreement (r={max_r:.2f} <= 0.65). Applying ensemble average fallback.")
        weights["precipitation"] = 0.33
        weights["vegetation"] = 0.33
        weights["soil_moisture"] = 0.34
        weights["fusion_type"] = "Ensemble Average Fallback"
        
    return weights

def clip_to_range(val, min_val, max_val):
    return max(min_val, min(val, max_val))

if __name__ == "__main__":
    # Test strong correlation weight derivation
    w_strong = derive_dynamic_correlation_weights(0.72, 0.68, 0.45)
    print(f"Strong weights: {w_strong}")
    
    # Test poor correlation fallback
    w_poor = derive_dynamic_correlation_weights(0.42, 0.35, 0.12)
    print(f"Poor weights: {w_poor}")
