"""
ENSOwatch AI -- drought assessor.
Deterministic risk scoring (always free) + optional LLM narrative.

Module API (all exported):
    compute_drought_score       -- core 0-100 risk score
    generate_summary            -- present-tense narrative
    generate_summary_past       -- past-tense narrative (hindsight mode)
    generate_recommendations    -- present-tense action items
    generate_observations_past  -- past-tense observations (hindsight mode)
    call_llm_narrative          -- optional Anthropic / OpenAI narrative

Build tag (bump on every deploy to confirm freshness): v3
"""
__build__ = "v3"
import numpy as np
import pandas as pd
from ensa.math.meteorology import calculate_spi3


# ──────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────

def compute_drought_score(
    df: pd.DataFrame,
    oni_value: float,
    crop_stage: str,
    is_active_season: bool,
) -> dict:
    """
    Returns a 0-100 drought risk score from real weather data.
    Inputs:
      df             — DataFrame from openmeteo.fetch_weather (must have precip_mm, temp_c, et0_mm)
      oni_value      — NINO3.4 SST anomaly (°C)
      crop_stage     — string from crop calendar (e.g. "Flowering & Tasseling")
      is_active_season — whether the crop is actively growing
    """
    if df is None or df.empty:
        return _empty()

    tail = df.tail(90).copy()

    total_precip = float(tail["precip_mm"].sum())
    total_et0 = float(tail["et0_mm"].sum())
    avg_temp = float(tail["temp_c"].mean())
    cumulative_deficit = max(0.0, total_et0 - total_precip)  # mm over-demand

    # SPI-3 (McKee 1993) — needs the full history for a proper fit
    spi_series = calculate_spi3(df["precip_mm"])
    spi3_now = float(spi_series[-1]) if len(spi_series) else 0.0

    # ── Precipitation component (0–40 pts) ───────────────────────────────
    if spi3_now <= -2.0:
        p_score = 40.0
    elif spi3_now <= -1.5:
        p_score = 30.0
    elif spi3_now <= -1.0:
        p_score = 20.0
    elif spi3_now <= -0.5:
        p_score = 10.0
    else:
        p_score = max(0.0, -spi3_now * 5.0)

    # ── Water-deficit component (0–40 pts) ───────────────────────────────
    if cumulative_deficit >= 250:
        d_score = 40.0
    elif cumulative_deficit >= 100:
        d_score = 20.0 + (cumulative_deficit - 100) * 0.133
    else:
        d_score = cumulative_deficit * 0.20

    # ── Temperature stress component (0–20 pts) ──────────────────────────
    t_score = min(20.0, max(0.0, (avg_temp - 25.0) * 3.0))

    # ── ENSO amplification ────────────────────────────────────────────────
    enso_amp = 1.0 + max(0.0, (oni_value - 0.5) * 0.20)
    enso_amp = min(1.5, enso_amp)

    # ── Crop-stage amplification ─────────────────────────────────────────
    _critical_keywords = ("flower", "tassel", "critical", "panicle", "jointing",
                          "heading", "silk", "booting")
    is_critical = any(kw in crop_stage.lower() for kw in _critical_keywords)
    stage_amp = 1.35 if is_critical else 1.0

    # ── Off-season dampener ───────────────────────────────────────────────
    season_mult = 1.0 if is_active_season else 0.25

    raw = (p_score + d_score + t_score) * enso_amp * stage_amp * season_mult
    score = min(100.0, round(raw, 1))

    # ── Alert level ───────────────────────────────────────────────────────
    if score >= 75:
        level, color, emoji = "Extreme",  "#B91C1C", "🚨"
    elif score >= 55:
        level, color, emoji = "Severe",   "#C2410C", "⚠️"
    elif score >= 35:
        level, color, emoji = "Warning",  "#B45309", "⚡"
    elif score >= 15:
        level, color, emoji = "Watch",    "#1E40AF", "👁️"
    else:
        level, color, emoji = "Normal",   "#15803D", "✅"

    return {
        "score": score,
        "alert_level": level,
        "alert_color": color,
        "alert_emoji": emoji,
        "spi3": round(spi3_now, 2),
        "cumulative_deficit_mm": round(cumulative_deficit, 1),
        "total_precip_90d_mm": round(total_precip, 1),
        "avg_temp_c": round(avg_temp, 1),
        "total_et0_90d_mm": round(total_et0, 1),
        "enso_amp": round(enso_amp, 2),
        "is_critical_stage": is_critical,
        "is_active_season": is_active_season,
    }


# ──────────────────────────────────────────────
# TEMPLATE NARRATIVE (no LLM — always free)
# ──────────────────────────────────────────────

def generate_summary(assessment: dict, crop_name: str, crop_stage: str,
                     oni_phase: str, location_name: str) -> str:
    level = assessment["alert_level"]
    precip = assessment["total_precip_90d_mm"]
    deficit = assessment["cumulative_deficit_mm"]
    temp = assessment["avg_temp_c"]
    off_season = "" if assessment["is_active_season"] else (
        f" Note: {crop_name} is currently in its off-season, "
        "so drought stress on the growing crop is low even if soil conditions are dry."
    )

    if level in ("Extreme", "Severe"):
        return (
            f"Conditions near {location_name} are under serious drought stress. "
            f"Only {precip:.0f} mm of rain fell in the last 90 days against an evaporation "
            f"demand of {assessment['total_et0_90d_mm']:.0f} mm — leaving a water deficit of "
            f"{deficit:.0f} mm. Average temperature is {temp:.1f}°C. "
            f"ENSO phase is {oni_phase.lower()}, which is suppressing normal rainfall patterns. "
            f"Your {crop_name} in the {crop_stage} stage is at high risk of significant yield loss "
            f"without immediate action.{off_season}"
        )
    elif level == "Warning":
        return (
            f"Conditions near {location_name} show moderate drought stress. "
            f"Rainfall over the last 90 days ({precip:.0f} mm) is below crop water requirements, "
            f"with a cumulative deficit of {deficit:.0f} mm. Temperature is {temp:.1f}°C. "
            f"ENSO phase is {oni_phase.lower()}. "
            f"Monitor your {crop_name} closely and prepare to irrigate if conditions worsen.{off_season}"
        )
    elif level == "Watch":
        return (
            f"Conditions near {location_name} are slightly drier than normal. "
            f"Rainfall over 90 days ({precip:.0f} mm) is below the evaporation demand "
            f"by {deficit:.0f} mm, but crops are not under acute stress yet. "
            f"ENSO phase is {oni_phase.lower()}. Stay alert and monitor weekly.{off_season}"
        )
    else:
        return (
            f"Conditions near {location_name} are within the normal range. "
            f"Rainfall over the last 90 days ({precip:.0f} mm) is adequate for the current season, "
            f"and temperatures ({temp:.1f}°C) are typical. "
            f"ENSO phase is {oni_phase.lower()}. "
            f"Continue standard field management for your {crop_name}.{off_season}"
        )


# ──────────────────────────────────────────────
# PAST-TENSE NARRATIVE (for hindsight / historical analysis mode)
# ──────────────────────────────────────────────

def generate_summary_past(assessment: dict, crop_name: str, crop_stage: str,
                          oni_phase: str, location_name: str,
                          target_date: str) -> str:
    """Past-tense summary for historical date analysis."""
    level   = assessment["alert_level"]
    precip  = assessment["total_precip_90d_mm"]
    deficit = assessment["cumulative_deficit_mm"]
    temp    = assessment["avg_temp_c"]
    et0     = assessment["total_et0_90d_mm"]
    off_season = "" if assessment["is_active_season"] else (
        f" Note: {crop_name} was in its off-season at this time, so observed "
        "dry conditions did not reflect active crop stress."
    )

    if level in ("Extreme", "Severe"):
        return (
            f"On **{target_date}**, conditions near {location_name} were under "
            f"serious drought stress. Only {precip:.0f} mm of rain had fallen "
            f"in the preceding 90 days against an evaporation demand of "
            f"{et0:.0f} mm — a cumulative water deficit of {deficit:.0f} mm. "
            f"Average temperature was {temp:.1f}°C. "
            f"ENSO phase was **{oni_phase.lower()}**. "
            f"The {crop_name} crop in the {crop_stage} stage faced high risk "
            f"of significant yield loss during this period.{off_season}"
        )
    elif level == "Warning":
        return (
            f"On **{target_date}**, conditions near {location_name} showed "
            f"moderate drought stress. Rainfall over the preceding 90 days "
            f"({precip:.0f} mm) was below crop water requirements, with a "
            f"cumulative deficit of {deficit:.0f} mm. Temperature averaged "
            f"{temp:.1f}°C. ENSO phase was **{oni_phase.lower()}**. "
            f"The {crop_name} crop required close monitoring during this "
            f"period.{off_season}"
        )
    elif level == "Watch":
        return (
            f"On **{target_date}**, conditions near {location_name} were "
            f"slightly drier than normal. Rainfall over the preceding 90 days "
            f"({precip:.0f} mm) trailed evaporation demand by {deficit:.0f} mm, "
            f"but crops were not under acute stress. ENSO phase was "
            f"**{oni_phase.lower()}**.{off_season}"
        )
    else:
        return (
            f"On **{target_date}**, conditions near {location_name} were "
            f"within the normal range. Rainfall over the preceding 90 days "
            f"({precip:.0f} mm) was adequate for the season, and temperatures "
            f"({temp:.1f}°C) were typical. ENSO phase was "
            f"**{oni_phase.lower()}**.{off_season}"
        )


def generate_observations_past(assessment: dict, crop_name: str,
                                crop_stage: str, oni_value: float,
                                target_date: str) -> list[str]:
    """
    Past-tense observations of what the crop and farm likely experienced.
    Returned as a list of evidence-based statements (not action items).
    """
    level   = assessment["alert_level"]
    deficit = assessment["cumulative_deficit_mm"]
    precip  = assessment["total_precip_90d_mm"]
    temp    = assessment["avg_temp_c"]
    is_critical = assessment["is_critical_stage"]
    is_active   = assessment["is_active_season"]
    obs = []

    if level in ("Extreme", "Severe"):
        obs.append(
            f"🌾 **Crop water stress was severe.** Rainfall ({precip:.0f} mm) "
            f"covered only a fraction of the {crop_name} crop's needs over "
            f"this 90-day period."
        )
        if is_critical:
            obs.append(
                f"💔 **Critical growth stage coincided with drought.** "
                f"{crop_stage} is the most water-sensitive phase — pollination "
                f"failure and irreversible yield loss were likely outcomes."
            )
        obs.append(
            f"🔥 **Cumulative deficit of {deficit:.0f} mm** indicates the soil "
            "moisture reserves were likely depleted, with topsoil drying out "
            "well into the root zone."
        )
        if temp > 28:
            obs.append(
                f"🌡️ **Heat compounded the stress.** Average temperature of "
                f"{temp:.1f}°C accelerated evapotranspiration and shortened "
                f"the effective grain-filling window."
            )
        if oni_value >= 1.5:
            obs.append(
                f"🌊 **Strong El Niño conditions** (NINO3.4 ≥ +1.5°C) were "
                "active. Across analogous past events, this teleconnection "
                "consistently suppressed regional monsoon and growing-season "
                "rainfall."
            )
        elif oni_value <= -1.0:
            obs.append(
                "🌊 **La Niña conditions** were active. The drought signal "
                "here would have run counter to the typical La Niña wet "
                "pattern — suggesting local factors dominated."
            )
        if is_active:
            obs.append(
                f"📉 **Likely outcome:** significant yield reduction for "
                f"{crop_name}. Farmers with irrigation access would have "
                f"depleted local water reserves; rainfed plots would have "
                f"shown visible canopy browning by the end of this window."
            )
    elif level == "Warning":
        obs.append(
            f"💧 **Moisture supply ran behind demand.** A {deficit:.0f} mm "
            f"deficit accumulated over 90 days; not catastrophic, but enough "
            f"to slow crop development."
        )
        if is_critical:
            obs.append(
                f"⚠️ **{crop_stage} stage was vulnerable.** Below-normal "
                "rainfall during this reproductive phase typically reduces "
                "final yield by 10-25%."
            )
        if temp > 28:
            obs.append(
                f"🌡️ Temperatures averaging {temp:.1f}°C added to "
                f"evapotranspiration stress."
            )
        if oni_value >= 0.5:
            obs.append(
                f"🌊 El Niño conditions were active (NINO3.4 "
                f"+{oni_value:.2f}°C), historically associated with drier "
                f"seasons in many crop regions."
            )
        obs.append(
            f"📊 **Likely outcome:** modest yield reduction relative to a "
            f"normal season for {crop_name}, with quality and grain weight "
            f"affected more than total grain count."
        )
    elif level == "Watch":
        obs.append(
            f"👁️ Conditions were drier than normal but not stressed. "
            f"A {deficit:.0f} mm gap between supply and demand built up over "
            f"the 90-day window."
        )
        obs.append(
            f"🌱 Crop growth would have proceeded near normal, with mild "
            f"slowing during peak demand periods."
        )
    else:
        obs.append(
            f"✅ **Conditions were favorable.** {precip:.0f} mm of rain met "
            f"or exceeded {crop_name} water requirements over the 90-day "
            f"window."
        )
        if oni_value <= -0.5:
            obs.append(
                f"🌊 La Niña conditions (NINO3.4 {oni_value:+.2f}°C) "
                f"were active — historically a wet pattern for many regions, "
                f"consistent with the observed rainfall surplus."
            )
        obs.append(
            f"🌾 **Likely outcome:** normal or above-normal yield for "
            f"{crop_name} given the favorable supply-demand balance."
        )
    if not is_active:
        obs.append(
            f"📅 Note: {crop_name} was in its off-season during this period, "
            f"so the drought score reflects climatology only, not active "
            f"crop stress."
        )
    return obs


def generate_recommendations(assessment: dict, crop_name: str,
                              crop_stage: str, oni_value: float) -> list[str]:
    level = assessment["alert_level"]
    deficit = assessment["cumulative_deficit_mm"]
    is_critical = assessment["is_critical_stage"]
    recs = []

    if level in ("Extreme", "Severe"):
        recs.append(
            f"🚿 **Irrigate immediately.** Your {crop_name} faces a {deficit:.0f} mm water deficit "
            "over the last 90 days. Every day without water increases permanent yield loss."
        )
        if is_critical:
            recs.append(
                f"🌱 **Critical growth stage.** {crop_stage} is when water stress causes the "
                "most damage — pollination failure and kernel abortion cannot be reversed."
            )
        recs.append(
            "💧 **Harvest every drop.** Clear furrows, ditches, and any on-farm storage to "
            "capture any rain that does fall."
        )
        recs.append(
            "🌾 **Mulch your topsoil.** A 5–10 cm layer of crop residue can cut evaporation "
            "losses by up to 40%."
        )
        recs.append(
            "📞 **Report to your extension officer.** Declare the drought condition so "
            "emergency seeds and food reserves can be prepared for your area."
        )
        if oni_value >= 1.5:
            recs.append(
                "🌊 **Strong El Niño.** Normal recovery rains are unlikely this season. "
                "Consider short-season drought-tolerant varieties for any replanting."
            )
    elif level == "Warning":
        recs.append(
            f"💧 **Supplement with irrigation** where possible — the 90-day deficit is "
            f"{deficit:.0f} mm and conditions may worsen."
        )
        recs.append(
            "🌾 **Hold off on heavy fertilizer.** Without water, nutrients cannot reach the roots "
            "and may burn the crop instead."
        )
        recs.append(
            "🐛 **Increase pest scouting.** Drought-stressed plants attract insects and are "
            "more susceptible to disease — check your crop twice a week."
        )
        recs.append(
            "🌱 **Check soil moisture 5–10 cm deep.** If the soil feels dry at that depth, "
            "your crop is already under root-zone stress."
        )
    elif level == "Watch":
        recs.append(
            "📊 **Monitor weekly.** Conditions are below normal but manageable. "
            "Check rainfall totals against your crop water requirements."
        )
        recs.append(
            "💧 **Prepare irrigation infrastructure.** Test pumps and drip lines so "
            "you can respond quickly if conditions worsen."
        )
        recs.append(
            "🌡️ **Watch for heat stress.** Temperatures are above average — early signs "
            "include leaf rolling and wilting in the afternoon."
        )
    else:
        recs.append(
            "✅ **Continue standard practices.** Rainfall and temperatures are within "
            f"the normal range for {crop_name}."
        )
        recs.append(
            "📊 **Keep records.** Log your rainfall, crop observations, and any stress "
            "symptoms — this builds your personal drought early-warning history."
        )

    return recs


# ──────────────────────────────────────────────
# OPTIONAL LLM NARRATIVE (user-supplied key)
# ──────────────────────────────────────────────

def call_llm_narrative(
    assessment: dict,
    crop_name: str,
    crop_stage: str,
    oni: dict,
    location_name: str,
    api_key: str,
    provider: str = "anthropic",
) -> str:
    """
    Calls Claude or OpenAI to generate a richer farmer-friendly paragraph.
    provider: "anthropic" | "openai"
    Returns the text, or an error message string.
    """
    prompt = (
        f"You are an agricultural drought advisor helping a smallholder farmer.\n\n"
        f"Location: {location_name}\n"
        f"Crop: {crop_name} (stage: {crop_stage})\n"
        f"Drought risk score: {assessment['score']}/100 ({assessment['alert_level']})\n"
        f"Rainfall last 90 days: {assessment['total_precip_90d_mm']} mm\n"
        f"Evaporation demand last 90 days: {assessment['total_et0_90d_mm']} mm\n"
        f"Cumulative water deficit: {assessment['cumulative_deficit_mm']} mm\n"
        f"Average temperature: {assessment['avg_temp_c']} °C\n"
        f"SPI-3 index: {assessment['spi3']} (below –1.0 = drought, below –2.0 = severe)\n"
        f"ENSO phase: {oni['phase']} (NINO3.4 anomaly = {oni['value']} °C)\n"
        f"Critical crop growth stage: {'Yes' if assessment['is_critical_stage'] else 'No'}\n\n"
        "Write a clear 3–4 sentence assessment for the farmer in plain language "
        "(no climate jargon). Then give 3 specific practical actions for this week. "
        "Use a warm, direct tone — you are talking to a farmer who depends on this crop."
    )

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content

    except ImportError as e:
        return f"SDK not installed: {e}. Run `pip install {provider}`."
    except Exception as e:
        return f"AI analysis failed: {e}"

    return ""


def _empty() -> dict:
    return {
        "score": 0.0, "alert_level": "Unknown", "alert_color": "#a0aec0",
        "alert_emoji": "❓", "spi3": 0.0, "cumulative_deficit_mm": 0.0,
        "total_precip_90d_mm": 0.0, "avg_temp_c": 0.0, "total_et0_90d_mm": 0.0,
        "enso_amp": 1.0, "is_critical_stage": False, "is_active_season": True,
    }
