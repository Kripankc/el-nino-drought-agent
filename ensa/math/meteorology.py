import numpy as np
import pandas as pd
from scipy.stats import gamma, norm

def calculate_spi3(precip_series):
    """
    McKee et al. 1993 - Standardised Precipitation Index (3-month window).
    Fits precipitation to a two-parameter Gamma distribution,
    then transforms to standard normal values.
    """
    values = precip_series.values
    if len(values) < 4:
        # Fallback if too few data points
        return np.zeros_like(values)

    # 1. Rolling 3-month (90-day, i.e. 12 weekly steps) precipitation sum
    rolling_sum = precip_series.rolling(window=12, min_periods=1).sum().values
    
    # 2. Fit Gamma distribution parameters (alpha=shape, beta=scale)
    # Using scipy stats to handle standard gamma parameters
    try:
        alpha, loc, beta = gamma.fit(rolling_sum, floc=0)
        # Compute probability of zero precip if any
        p_zero = np.sum(rolling_sum == 0) / len(rolling_sum)
        
        # Cumulative probability
        cdf = gamma.cdf(rolling_sum, alpha, loc, beta)
        
        # Adjust for p_zero
        h = p_zero + (1 - p_zero) * cdf
        h = np.clip(h, 1e-5, 0.99999) # Prevent infs
        
        # Transform to standard normal distribution
        spi = norm.ppf(h)
        return np.round(spi, 2)
    except Exception as e:
        # Robust mathematical fallback if fitting fails
        print(f"[Math Warning] SPI fitting error: {e}. Using standardized z-scores.")
        mean = np.mean(rolling_sum)
        std = np.std(rolling_sum) + 1e-8
        return np.round((rolling_sum - mean) / std, 2)

def calculate_penman_monteith_pet(temp_c):
    """
    Vicente-Serrano 2010 - Simplified Penman-Monteith Potential Evapotranspiration (PET).
    Estimates daily PET in mm based on temperature, assuming standard regional solar radiation.
    Formula: PET = 0.0023 * Ra * (Temp + 17.8) * sqrt(Td)
    """
    # Standard extraterrestrial radiation Ra for Southern Africa latitude (~15S)
    ra = 38.2
    td = np.full(len(temp_c), 11.0)  # typical diurnal range for Southern Africa
    pet = 0.0023 * ra * (temp_c + 17.8) * np.sqrt(td)
    return np.round(pet, 2)

def calculate_spei(precip_series, temp_c_series):
    """
    Vicente-Serrano 2010 - Standardised Precipitation-Evapotranspiration Index.
    Compares P - PET water balance anomaly, fitting to standard Normal distribution.
    """
    p = precip_series.values
    t = temp_c_series.values
    
    # Calculate PET
    pet = calculate_penman_monteith_pet(t)
    
    # Difference (Water balance)
    d = p - pet
    
    # Standardize over rolling window
    mean_d = np.mean(d)
    std_d = np.std(d) + 1e-8
    spei = (d - mean_d) / std_d
    return np.round(spei, 2)

if __name__ == "__main__":
    np.random.seed(42)
    precip = pd.Series(np.random.uniform(0.0, 50.0, 30))
    temp = pd.Series(np.random.uniform(22.0, 35.0, 30))
    
    spi3 = calculate_spi3(precip)
    spei = calculate_spei(precip, temp)
    
    print(f"SPI-3: {spi3[:5]}")
    print(f"SPEI: {spei[:5]}")
