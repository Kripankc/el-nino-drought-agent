"""
Hindsight analysis: compare past-date observations against
climatology baselines and ENSO-conditional expectations.

For a chosen past date we contrast:
  1. Climatology baseline -- the long-term mean rainfall for the surrounding
     calendar window (what a naive forecast would have predicted).
  2. ENSO-conditional baseline -- the mean rainfall in past seasons whose
     ENSO phase matches the actual phase at the time of the selected date
     (what an ENSO-aware forecast would have predicted).
  3. Observed -- actual ERA5 reanalysis rainfall around the date.

The story it tells the farmer:
  "Would knowing the ENSO state have helped predict this season's outcome?"
"""
import numpy as np
import pandas as pd

from ensa.ingest.enso import classify_oni


def _phase_of(oni_value):
    return classify_oni(oni_value)


def hindsight_compare(
    df_clim: pd.DataFrame,
    df_observed: pd.DataFrame,
    oni_hist: dict,
    target_date: pd.Timestamp,
    window_days: int = 90,
) -> dict:
    """
    Inputs:
      df_clim       -- multi-decade daily history (precip_mm, temp_c) for this location
      df_observed   -- ERA5 window already centred on target_date (must contain target_date)
      oni_hist      -- {(year, month): anomaly} from enso.fetch_oni_history()
      target_date   -- the past date the user picked
      window_days   -- rolling window length for cumulative comparison

    Returns dict:
      ok                  -- bool
      target_date         -- ISO string
      enso_then           -- {value, phase, year, month}
      observed_precip     -- mm in the window ENDING on target_date
      observed_temp       -- mean C in that window
      climatology_precip  -- long-term mean for that same calendar window
      enso_conditional_precip -- mean for seasons whose ONI matched
      delta_vs_clim       -- observed - climatology  (mm)
      delta_vs_enso       -- observed - enso_conditional (mm)
      enso_skill_pct      -- how much closer the ENSO forecast got to observed
                              vs. naive climatology, as a percentage
      reason              -- diagnostic if ok is False
    """
    target = pd.Timestamp(target_date).normalize()
    if df_clim is None or df_clim.empty:
        return {"ok": False, "reason": "no climatology"}
    if df_observed is None or df_observed.empty:
        return {"ok": False, "reason": "no observation window"}

    # --- ENSO state on that date ---------------------------------------
    oni_then = oni_hist.get((target.year, target.month))
    if oni_then is None:
        # try previous month if very early in current month
        oni_then = oni_hist.get((target.year, max(1, target.month - 1)))
    enso_then = {
        "value": round(float(oni_then), 2) if oni_then is not None else None,
        "phase": _phase_of(oni_then) if oni_then is not None else "Unknown",
        "year":  int(target.year),
        "month": int(target.month),
    }

    # --- Observed window (window_days days ending on target_date) ------
    obs = df_observed[(df_observed["date"] <= target) &
                      (df_observed["date"] >= target - pd.Timedelta(days=window_days))]
    if obs.empty:
        return {"ok": False, "reason": "observed window empty"}
    observed_precip = float(obs["precip_mm"].sum())
    observed_temp   = float(obs["temp_c"].mean())

    # --- Climatology baseline: same calendar window across all years ---
    df = df_clim.copy()
    df["doy"] = df["date"].dt.dayofyear
    target_doy = target.dayofyear
    start_doy  = (target_doy - window_days) % 366 or 366

    # Pull the same day-of-year window from every year in the archive.
    # Handle wrap-around (start_doy > target_doy means we cross Dec 31).
    if start_doy <= target_doy:
        mask = (df["doy"] >= start_doy) & (df["doy"] <= target_doy)
    else:
        mask = (df["doy"] >= start_doy) | (df["doy"] <= target_doy)

    df_window = df[mask].copy()
    df_window["year"] = df_window["date"].dt.year
    # If wrap, label each row to the year the window ENDS in
    if start_doy > target_doy:
        df_window["window_year"] = np.where(
            df_window["doy"] >= start_doy,
            df_window["year"] + 1,
            df_window["year"],
        )
    else:
        df_window["window_year"] = df_window["year"]

    yearly = df_window.groupby("window_year")["precip_mm"].sum().reset_index()
    yearly = yearly[yearly["window_year"] < target.year]  # exclude target year itself
    yearly = yearly[yearly["window_year"] >= 1985]
    if len(yearly) < 6:
        return {"ok": False, "reason": "climatology too short"}
    clim_precip = float(yearly["precip_mm"].mean())

    # --- ENSO-conditional baseline: same window in past seasons whose ONI
    #     averaged to the same phase as the current ENSO state. ----------
    enso_cond_precip = None
    if oni_then is not None:
        target_phase = _phase_of(oni_then)
        # For each historical year of this window, compute the mean ONI over
        # the window's months and assign a phase.
        oni_per_year = []
        for y in yearly["window_year"]:
            vals = []
            # Months in the window for that year
            d = pd.Timestamp(year=int(y), month=int(target.month), day=int(target.day)) \
                if target.month != 2 or target.day <= 28 else \
                pd.Timestamp(year=int(y), month=2, day=28)
            start_d = d - pd.Timedelta(days=window_days)
            cur = start_d
            seen = set()
            while cur <= d:
                key = (cur.year, cur.month)
                if key not in seen:
                    seen.add(key)
                    v = oni_hist.get(key)
                    if v is not None:
                        vals.append(v)
                cur += pd.Timedelta(days=15)
            if vals:
                mean_oni = float(np.mean(vals))
                oni_per_year.append((int(y), mean_oni, _phase_of(mean_oni)))

        matched = [y for (y, o, p) in oni_per_year if p == target_phase]
        if len(matched) >= 3:
            enso_cond_precip = float(
                yearly[yearly["window_year"].isin(matched)]["precip_mm"].mean()
            )

    # --- Deltas and skill ---------------------------------------------
    delta_vs_clim = observed_precip - clim_precip
    delta_vs_enso = (observed_precip - enso_cond_precip) if enso_cond_precip is not None else None

    skill_pct = None
    if enso_cond_precip is not None and clim_precip > 0:
        err_clim = abs(observed_precip - clim_precip)
        err_enso = abs(observed_precip - enso_cond_precip)
        if err_clim > 0:
            skill_pct = round(((err_clim - err_enso) / err_clim) * 100, 1)

    return {
        "ok": True,
        "target_date":             target.strftime("%Y-%m-%d"),
        "window_days":             window_days,
        "enso_then":               enso_then,
        "observed_precip":         round(observed_precip, 1),
        "observed_temp":           round(observed_temp, 1),
        "climatology_precip":      round(clim_precip, 1),
        "enso_conditional_precip": (round(enso_cond_precip, 1)
                                    if enso_cond_precip is not None else None),
        "delta_vs_clim":           round(delta_vs_clim, 1),
        "delta_vs_enso":           (round(delta_vs_enso, 1)
                                    if delta_vs_enso is not None else None),
        "enso_skill_pct":          skill_pct,
        "n_climatology_years":     int(len(yearly)),
    }
