"""CropScope Kisan Mitra (किसान मित्र) Grounded RAG Chatbot Engine.

Provides hyper-local, grounded agricultural intelligence and multilingual chat
support for Indian farmers, using real-time satellite canopy analytics and 7-day
agro-climatic water balance forecasts.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from agronomy import (
    compute_agro_climatic_summary,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_growth_stage_guidance,
    summarize_canopy_health,
)
from analysis import AnalysisOutcome
from i18n import SUPPORTED_LANGUAGES, t
from models import SatelliteResult, WeatherResult

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_TIMEOUT_MS = 25_000


def get_dossier_summary_stats(outcome: AnalysisOutcome) -> Dict[str, Any]:
    """Extract key numerical and qualitative metrics from an analysis outcome."""
    req = outcome.request
    area = req.area
    lat_center, lon_center = area.center

    stats: Dict[str, Any] = {
        "crop": req.crop,
        "growth_stage": req.growth_stage,
        "growth_stage_guidance": get_growth_stage_guidance(req.growth_stage),
        "area_formatted": area.formatted_area(),
        "center_lat": round(lat_center, 5),
        "center_lon": round(lon_center, 5),
        "bbox": {
            "south": round(area.south, 5),
            "west": round(area.west, 5),
            "north": round(area.north, 5),
            "east": round(area.east, 5),
        },
        "weather_available": False,
        "satellite_available": False,
        "total_rain_7d_mm": 0.0,
        "total_et0_7d_mm": 0.0,
        "net_water_balance_mm": 0.0,
        "water_balance_status": "Unknown",
        "imminent_rain_48h_mm": 0.0,
        "safe_to_spray_next_48h": True,
        "peak_rain_day": None,
        "peak_rain_mm": 0.0,
        "spraying_favorable_days_count": 0,
        "machinery_accessible_days_count": 0,
        "mean_ndvi": None,
        "mean_savi": None,
        "cloud_cover_pct": None,
        "valid_pixels_pct": None,
        "canopy_summary": "",
        "canopy_zones": {},
        "suggestions_count": len(outcome.suggestions),
    }

    # Weather extraction
    weather_res = outcome.weather.result
    if isinstance(weather_res, WeatherResult) and weather_res.days:
        stats["weather_available"] = True
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)

        stats["total_rain_7d_mm"] = summary.total_rain_mm
        stats["total_et0_7d_mm"] = summary.total_et0_mm
        stats["net_water_balance_mm"] = summary.net_balance_mm
        stats["water_balance_status"] = summary.status_label
        stats["spraying_favorable_days_count"] = len(windows.spraying_favorable_days)
        stats["machinery_accessible_days_count"] = len(windows.machinery_accessible_days)

        # 48h rain outlook (first 2 forecast days)
        first_48h_days = weather_res.days[:2]
        rain_48h = sum(d.rain_mm for d in first_48h_days)
        stats["imminent_rain_48h_mm"] = round(rain_48h, 2)
        # Unsafe to spray if imminent rain >= 2.0 mm or max temp >= 35°C
        stats["safe_to_spray_next_48h"] = (
            rain_48h < 2.0 and all(d.max_temp_c < 35.0 for d in first_48h_days)
        )

        peak_day = max(weather_res.days, key=lambda d: d.rain_mm)
        stats["peak_rain_day"] = str(peak_day.day)
        stats["peak_rain_mm"] = round(peak_day.rain_mm, 1)

    # Satellite extraction
    sat_res = outcome.satellite.result
    if isinstance(sat_res, SatelliteResult):
        stats["satellite_available"] = True
        stats["mean_ndvi"] = sat_res.mean_ndvi
        stats["mean_savi"] = sat_res.mean_savi
        stats["cloud_cover_pct"] = sat_res.scene_cloud_percent
        stats["valid_pixels_pct"] = sat_res.valid_pixel_percent
        stats["canopy_zones"] = sat_res.canopy_zones or {}
        stats["canopy_summary"] = summarize_canopy_health(sat_res.canopy_zones)

    return stats


def build_farmer_dossier(outcome: AnalysisOutcome, lang: str = "en") -> str:
    """Build a comprehensive, grounded field intelligence dossier for LLM context.

    This acts as the hyper-local ground-truth document for RAG generation, preventing
    hallucination and grounding all advice in this exact field's satellite pass and weather.
    """
    stats = get_dossier_summary_stats(outcome)
    req = outcome.request
    area = req.area
    lat_center, lon_center = area.center

    lines: List[str] = [
        "=== CROP & FIELD INTELLIGENCE GROUND-TRUTH DOSSIER ===",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## 1. FIELD GEOMETRY & LOCATION",
        f"- Target Crop: {req.crop or 'Unspecified Crop'}",
        f"- Growth Stage: {req.growth_stage or 'Unspecified'} ({stats['growth_stage_guidance']})",
        f"- Center Coordinates: Latitude {lat_center:.5f}°, Longitude {lon_center:.5f}°",
        f"- Geographic Bounding Box: [South: {area.south:.5f}°, West: {area.west:.5f}°, North: {area.north:.5f}°, East: {area.east:.5f}°]",
        f"- Field Area Extent: {area.formatted_area()}",
        "",
    ]

    # Weather & Water Balance
    lines.append("## 2. SEVEN-DAY AGRO-CLIMATIC & WATER BALANCE FORECAST")
    weather_res = outcome.weather.result
    if isinstance(weather_res, WeatherResult) and weather_res.days:
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)
        alerts = generate_weather_alerts(weather_res)

        lines.extend([
            f"- Cumulative 7-Day Rainfall (P): {summary.total_rain_mm:.1f} mm",
            f"- Cumulative 7-Day Evapotranspiration (ET₀): {summary.total_et0_mm:.1f} mm",
            f"- Net Atmospheric Water Balance (P − ET₀): {summary.net_balance_mm:+.1f} mm ({summary.status_label})",
            f"- Imminent 48-Hour Rain Forecast: {stats['imminent_rain_48h_mm']:.1f} mm",
            f"- Spray Safety Window Next 48h: {'FAVORABLE' if stats['safe_to_spray_next_48h'] else 'UNFAVORABLE / CAUTION (risk of rain wash-off or heat)'}",
            f"- Peak Rain Day: {stats['peak_rain_day']} with {stats['peak_rain_mm']:.1f} mm rain",
            f"- Favorable Fieldwork Days: {summary.favorable_days_count} of {len(summary.days)} days",
            f"- Spraying Suitable Dates: {', '.join(str(d) for d in windows.spraying_favorable_days) if windows.spraying_favorable_days else 'None in 7-day forecast'}",
            f"- Machinery Accessible Dates: {', '.join(str(d) for d in windows.machinery_accessible_days) if windows.machinery_accessible_days else 'None'}",
            "",
            "### Daily Meteorological Breakdown:",
            "| Date | Max Temp (°C) | Rain (mm) | ET₀ (mm) | Net Balance (mm) | Field Suitability | Reason |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ])
        for d in summary.days:
            lines.append(
                f"| {d.day} | {d.max_temp_c:.1f}°C | {d.rain_mm:.1f} mm | {d.et0_mm:.1f} mm | {d.net_balance_mm:+.1f} mm | {d.suitability} | {d.reason} |"
            )

        if alerts:
            lines.append("")
            lines.append("### Active Operational Weather Alerts:")
            for alert in alerts:
                lines.append(f"- [{alert.level.upper()}] {alert.category.title()}: {alert.message}")
    else:
        err_msg = outcome.weather.error or "Weather forecast data is currently unavailable."
        lines.append(f"- Status: Weather unavailable ({err_msg})")

    lines.append("")

    # Satellite Vegetation Health
    lines.append("## 3. SENTINEL-2 SATELLITE MULTISPECTRAL CANOPY HEALTH")
    sat_res = outcome.satellite.result
    if isinstance(sat_res, SatelliteResult):
        ndvi_val = f"{sat_res.mean_ndvi:.3f}" if sat_res.mean_ndvi is not None else "N/A"
        savi_val = f"{sat_res.mean_savi:.3f}" if sat_res.mean_savi is not None else "N/A"
        acq_date_str = (
            sat_res.acquired_at_utc.strftime("%Y-%m-%d %H:%M UTC")
            if getattr(sat_res, "acquired_at_utc", None)
            else "Unknown"
        )
        cloud_pct_val = (
            f"{sat_res.scene_cloud_percent:.1f}%"
            if sat_res.scene_cloud_percent is not None
            else "N/A"
        )
        valid_px_val = (
            f"{sat_res.valid_pixel_percent:.1f}%"
            if sat_res.valid_pixel_percent is not None
            else "N/A"
        )
        lines.extend([
            f"- Satellite Scene ID: {sat_res.scene_id}",
            f"- Scene Acquisition Date: {acq_date_str}",
            f"- Regional Scene Cloud Cover: {cloud_pct_val}",
            f"- Field Valid Optical Pixels (Cloud/Shadow Free): {valid_px_val}",
            f"- Field Mean NDVI (Normalized Difference Vegetation Index, -1.0 to +1.0): {ndvi_val}",
            f"- Field Mean SAVI (Soil-Adjusted Vegetation Index, L=0.5): {savi_val}",
            f"- High-Level Canopy Takeaway: {stats['canopy_summary'] or 'Normal vegetative canopy'}",
        ])
        if sat_res.canopy_zones:
            lines.append("")
            lines.append("### Canopy Density Zonation Breakdown:")
            for zone_name, pct in sat_res.canopy_zones.items():
                lines.append(f"- {zone_name}: {pct:.1f}% of field area")
    else:
        err_msg = outcome.satellite.error or "Satellite imagery pass is currently unavailable."
        lines.append(f"- Status: Satellite data unavailable ({err_msg})")

    lines.append("")

    # Field Action Checks & Agronomic Recommendations
    lines.append("## 4. PRIORITIZED FIELD ACTION CHECKS")
    if outcome.suggestions:
        source_label = outcome.suggestion_source or "Rule-based Agronomic Engine"
        lines.append(f"- Recommendation Engine: {source_label}")
        for idx, item in enumerate(outcome.suggestions, 1):
            lines.append(f"\n### Action Check {idx}: {item.candidate.title}")
            lines.append(f"- Practical Action: {item.candidate.action}")
            evidence_str = " ".join(e.text for e in item.evidence)
            lines.append(f"- Verified Field Evidence: {evidence_str}")
    else:
        lines.append("- No action checks triggered for this field configuration.")

    lines.extend([
        "",
        "=== END OF GROUND-TRUTH DOSSIER ===",
    ])
    return "\n".join(lines)


def generate_fallback_response(
    query: str,
    stats: Dict[str, Any],
    lang: str = "en",
) -> str:
    """Generate a reliable, grounded rule-based advisory response when LLM is unavailable."""
    q_lower = query.lower()
    crop = stats.get("crop") or "Crop"
    rain_7d = stats.get("total_rain_7d_mm", 0.0)
    rain_48h = stats.get("imminent_rain_48h_mm", 0.0)
    peak_day = stats.get("peak_rain_day") or "upcoming days"
    peak_mm = stats.get("peak_rain_mm", 0.0)
    safe_spray = stats.get("safe_to_spray_next_48h", True)
    ndvi = stats.get("mean_ndvi")
    net_bal = stats.get("net_water_balance_mm", 0.0)

    # 1. Rain / Weather intent
    rain_keywords = ["rain", "barish", "weather", "forecast", "बारिश", "मौसम", "ਮੀਂਹ", "पाऊस", "వర్షం", "மழை", "વરસાદ", "বৃষ্টি", "ಮಳೆ", "മഴ"]
    if any(k in q_lower for k in rain_keywords):
        if lang == "hi":
            return (
                f"🌧️ **मौसम व वर्षा रिपोर्ट ({crop}):**\n\n"
                f"- अगले 7 दिनों में कुल **{rain_7d:.1f} मिमी** बारिश का अनुमान है।\n"
                f"- अगले 48 घंटों में लगभग **{rain_48h:.1f} मिमी** बारिश की संभावना है।\n"
                f"- सबसे अधिक बारिश का दिन: **{peak_day}** (अनुमानित **{peak_mm:.1f} मिमी**)।\n\n"
                f"💡 *सलाह:* {'अगले 48 घंटे में मौसम अपेक्षाकृत सूखा है, सामान्य कार्य कर सकते हैं।' if rain_48h < 2.0 else 'बारिश आने वाली है, खेत में जल निकासी की व्यवस्था रखें।'}"
            )
        elif lang == "pa":
            return (
                f"🌧️ **ਮੌਸਮ ਅਤੇ ਮੀਂਹ ਦੀ ਜਾਣਕਾਰੀ ({crop}):**\n\n"
                f"- ਅਗਲੇ 7 ਦਿਨਾਂ ਵਿੱਚ ਕੁੱਲ **{rain_7d:.1f} ਮਿਮੀ** ਮੀਂਹ ਪੈਣ ਦੀ ਸੰਭਾਵਨਾ ਹੈ।\n"
                f"- ਅਗਲੇ 48 ਘੰਟਿਆਂ ਵਿੱਚ ਲਗਭਗ **{rain_48h:.1f} ਮਿਮੀ** ਮੀਂਹ ਆ ਸਕਦਾ ਹੈ।\n"
                f"- ਸਭ ਤੋਂ ਵੱਧ ਮੀਂਹ **{peak_day}** ਨੂੰ (**{peak_mm:.1f} ਮਿਮੀ**) ਹੋ ਸਕਦਾ ਹੈ।"
            )
        else:
            return (
                f"🌧️ **Weather & Rainfall Outlook for {crop}:**\n\n"
                f"- 7-day cumulative rainfall: **{rain_7d:.1f} mm**.\n"
                f"- Imminent 48-hour rainfall: **{rain_48h:.1f} mm**.\n"
                f"- Peak rain day: **{peak_day}** with **{peak_mm:.1f} mm** expected.\n\n"
                f"💡 *Agronomic note:* {'No immediate heavy rain; operational windows are favorable.' if rain_48h < 2.0 else 'Rain expected; check field drainage and hold sensitive operations.'}"
            )

    # 2. Spray / Pesticide / Fertilizer intent
    spray_keywords = ["spray", "pesticide", "fertilizer", "छिड़काव", "स्प्रे", "कीटनाशक", "खाद", "ਸਪਰੇਅ", "फवारणी", "పిచिकారీ", "தெளிக்க", "છાંટવું", "কীটনাশক", "ಸಿಂಪರಣೆ", "തളിക്ക"]
    if any(k in q_lower for k in spray_keywords):
        if safe_spray:
            if lang == "hi":
                return (
                    f"🚜 **छिड़काव (Spray) सलाह:**\n\n"
                    f"✅ **हाँ, अगले 48 घंटे में छिड़काव के लिए स्थिति अनुकूल है।**\n"
                    f"- 48 घंटे में भारी बारिश का खतरा नहीं है (केवल {rain_48h:.1f} मिमी अनुमानित)।\n"
                    f"- तेज धूप या अत्यधिक गर्मी से बचने के लिए सुबह या शाम को छिड़काव करें।\n\n"
                    f"⚠️ *सुरक्षा सूचना:* हमेशा अनुमोदित कीटनाशक की सही मात्रा का उपयोग करें और दवा के पैकेट पर दिए निर्देश पढ़ें।"
                )
            elif lang == "pa":
                return (
                    f"🚜 **ਸਪਰੇਅ ਸੰਬੰਧੀ ਸਲਾਹ:**\n\n"
                    f"✅ **ਹਾਂ, ਅਗਲੇ 48 ਘੰਟਿਆਂ ਵਿੱਚ ਸਪਰੇਅ ਕਰਨ ਲਈ ਮੌਸਮ ਅਨੁਕੂਲ ਹੈ।**\n"
                    f"- ਮੀਂਹ ਦੀ ਸੰਭਾਵਨਾ ਘੱਟ ਹੈ ({rain_48h:.1f} ਮਿਮੀ)।\n"
                    f"- ਸਪਰੇਅ ਹਮੇਸ਼ਾ ਸਵੇਰੇ ਜਾਂ ਸ਼ਾਮ ਵੇਲੇ ਕਰੋ ਤਾਂ ਜੋ ਦਵਾਈ ਦਾ ਪੂਰਾ ਅਸਰ ਹੋਵੇ।"
                )
            else:
                return (
                    f"🚜 **Spraying Advisory for {crop}:**\n\n"
                    f"✅ **Favorable window:** Operational conditions are currently favorable for spraying.\n"
                    f"- Low imminent rain risk ({rain_48h:.1f} mm in next 48h).\n"
                    f"- Recommended timing: Apply early morning or late afternoon when winds are calm (<15 km/h) and temperature is below 32°C.\n\n"
                    f"⚠️ *Safety:* Verify official chemical dosages on the product label or with your local agriculture extension officer."
                )
        else:
            if lang == "hi":
                return (
                    f"🚜 **छिड़काव (Spray) चेतावनी:**\n\n"
                    f"⚠️ **सावधानी: अगले 48 घंटों में कीटनाशक या खाद का छिड़काव न करें!**\n"
                    f"- अगले 48 घंटों में **{rain_48h:.1f} मिमी** बारिश का अनुमान है।\n"
                    f"- बारिश से छिड़की गई दवा बह जाएगी (wash-off), जिससे फसल को लाभ नहीं मिलेगा और पैसे का नुकसान होगा।\n"
                    f"- बारिश रुकने और खेत सूखने के बाद ही छिड़काव की योजना बनाएं।"
                )
            elif lang == "pa":
                return (
                    f"🚜 **ਸਪਰੇਅ ਚੇਤਾਵਨੀ:**\n\n"
                    f"⚠️ **ਸਾਵਧਾਨੀ: ਅਗਲੇ 48 ਘੰਟਿਆਂ 'ਚ ਸਪਰੇਅ ਨਾ ਕਰੋ!**\n"
                    f"- ਆਉਣ ਵਾਲੇ 48 ਘੰਟਿਆਂ 'ਚ **{rain_48h:.1f} ਮਿਮੀ** ਮੀਂਹ ਪੈ ਸਕਦਾ ਹੈ।\n"
                    f"- ਮੀਂਹ ਕਾਰਨ ਦਵਾਈ ਧੁਲ ਜਾਵੇਗੀ ਅਤੇ ਖਰਚਾ ਵਿਅਰਥ ਜਾਵੇਗਾ। ਮੀਂਹ ਰੁਕਣ ਮਗਰੋਂ ਸਪਰੇਅ ਕਰੋ।"
                )
            else:
                return (
                    f"🚜 **Spraying Warning for {crop}:**\n\n"
                    f"⚠️ **UNFAVORABLE: Hold chemical spraying for the next 48 hours.**\n"
                    f"- Forecast rain ({rain_48h:.1f} mm) or high thermal stress poses a serious risk of foliar wash-off or droplet volatilization.\n"
                    f"- Postpone application until the rain front clears and canopy surfaces are dry."
                )

    # 3. Satellite / NDVI / Canopy health intent
    canopy_keywords = ["ndvi", "satellite", "canopy", "health", "greenness", "हरापन", "सेहत", "तस्वीर", "तंदुरुस्ती", "ਫ਼ਸਲ", "आरोग्य", "ಬೆಳೆ", "பயிர்"]
    if any(k in q_lower for k in canopy_keywords):
        ndvi_str = f"{ndvi:.2f}" if ndvi is not None else "उपलब्ध नहीं"
        summary = stats.get("canopy_summary") or "Canopy healthy"
        if lang == "hi":
            return (
                f"🌿 **सैटेलाइट फसल स्वास्थ्य रिपोर्ट (Sentinel-2):**\n\n"
                f"- फसल का औसत हरापन (NDVI): **{ndvi_str}** (पैमाना: 0.0 से 1.0)।\n"
                f"- निष्कर्ष: {summary}\n"
                f"- बादलों से मुक्त साफ़ डेटा: **{stats.get('valid_pixels_pct', 100):.1f}%**।\n\n"
                f"💡 *सरल शब्दों में:* NDVI फसल के पत्तों के फैलाव और क्लोरोफिल की मात्रा बताता है। 0.5 से अधिक मान स्वस्थ हरी फसल का संकेत देता है।"
            )
        elif lang == "pa":
            return (
                f"🌿 **ਸੈਟੇਲਾਈਟ ਫ਼ਸਲ ਰਿਪੋਰਟ (Sentinel-2):**\n\n"
                f"- ਫ਼ਸਲ ਦਾ ਹਰਾਪਨ (NDVI): **{ndvi_str}**।\n"
                f"- ਸਮੁੱਚੀ ਸਿਹਤ: {summary}\n"
                f"- ਸਾਫ਼ ਸੈਟੇਲਾਈਟ ਡਾਟਾ: **{stats.get('valid_pixels_pct', 100):.1f}%**।"
            )
        else:
            return (
                f"🌿 **Satellite Vegetation Health (Sentinel-2 10m):**\n\n"
                f"- Mean NDVI (Canopy Greenness): **{ndvi_str}**.\n"
                f"- Mean SAVI (Soil-Adjusted Index): **{stats.get('mean_savi', 'N/A')}**.\n"
                f"- Canopy takeaway: {summary}\n"
                f"- Cloud-free optical accuracy: **{stats.get('valid_pixels_pct', 100):.1f}%**."
            )

    # 4. Irrigation / Water balance intent
    water_keywords = ["water", "irrigation", "sinchai", "moisture", "पानी", "सिंचाई", "ਨਮੀ", "ਪਾਣੀ", "ਨੀరు", "పాசனம்", "પિયત", "সেচ", "ನೀರಾವರಿ"]
    if any(k in q_lower for k in water_keywords):
        if lang == "hi":
            return (
                f"💧 **जल संतुलन व सिंचाई सलाह ({crop}):**\n\n"
                f"- 7 दिनों में संभावित वर्षा: **{rain_7d:.1f} मिमी**।\n"
                f"- धूप व हवा से नमी हानि (ET₀): **{stats.get('total_et0_7d_mm', 0.0):.1f} मिमी**।\n"
                f"- शुद्ध जल संतुलन (वर्षा − नमी हानि): **{net_bal:+.1f} मिमी** ({stats.get('water_balance_status', '')})।\n\n"
                f"💡 *सलाह:* {'मिट्टी में नमी की कमी हो सकती है, यदि वर्षा न हो तो हल्की सिंचाई की योजना बनाएं।' if net_bal < -10 else 'वर्षा से पर्याप्त नमी उपलब्ध है, अतिरिक्त सिंचाई की तुरंत आवश्यकता नहीं है।'}"
            )
        else:
            return (
                f"💧 **Agro-Climatic Water Balance & Irrigation ({crop}):**\n\n"
                f"- Cumulative 7-day rainfall: **{rain_7d:.1f} mm**.\n"
                f"- Reference evapotranspiration (ET₀): **{stats.get('total_et0_7d_mm', 0.0):.1f} mm**.\n"
                f"- Net water balance (P − ET₀): **{net_bal:+.1f} mm** ({stats.get('water_balance_status', '')}).\n\n"
                f"💡 *Recommendation:* {'Moisture deficit trend; plan scheduled irrigation if soil dry-down occurs.' if net_bal < -10 else 'Moisture accumulation or neutral balance; hold irrigation until topsoil dries.'}"
            )

    # Default overview
    if lang == "hi":
        return (
            f"🌾 **नमस्ते किसान भाई! मैं आपका किसान मित्र (CropScope AI) हूँ।**\n\n"
            f"- आपकी **{crop}** की फसल ({stats.get('growth_stage', 'सामान्य चरण')}) के लिए:\n"
            f"- 7-दिवसीय वर्षा: **{rain_7d:.1f} मिमी** | फसल हरापन (NDVI): **{ndvi if ndvi is not None else 'N/A'}**\n"
            f"- छिड़काव स्थिति: **{'अनुकूल' if safe_spray else 'सावधानी (बारिश का खतरा)'}**\n\n"
            f"आप मुझसे मौसम, खाद/कीटनाशक छिड़काव, पानी या फसल की सेहत के बारे में कोई भी प्रश्न पूछ सकते हैं!"
        )
    else:
        return (
            f"🌾 **Welcome! I am Kisan Mitra, your CropScope Field Advisor.**\n\n"
            f"- Target Field: **{crop}** ({stats.get('growth_stage', 'Active stage')})\n"
            f"- 7-Day Rainfall: **{rain_7d:.1f} mm** | Mean NDVI Greenness: **{ndvi if ndvi is not None else 'N/A'}**\n"
            f"- 48h Spray Window: **{'Favorable' if safe_spray else 'Caution / Postpone (rain risk)'}**\n\n"
            f"Feel free to ask me anything about weather forecast, irrigation need, spraying suitability, or canopy health!"
        )


def chat_with_kisan_mitra(
    messages: List[Dict[str, str]],
    dossier: str,
    stats: Optional[Dict[str, Any]] = None,
    lang: str = "en",
    *,
    api_key: Optional[str] = None,
) -> str:
    """Chat with Kisan Mitra grounded on the provided field dossier and language.

    Uses Gemini API when configured and available, with graceful automatic fallback
    to the grounded rule-based engine.
    """
    if not messages:
        return ""

    latest_query = messages[-1].get("content", "").strip()
    if not latest_query:
        return ""

    # Load API key
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")

    if key:
        target_meta = SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES["en"])
        lang_label = target_meta.get("label", "English")
        lang_native = target_meta.get("native", "English")

        system_instruction = (
            f"You are Kisan Mitra (किसान मित्र), a warm, trusted, expert Krishi Vigyan Kendra (KVK) agronomist and digital field advisor assisting Indian farmers.\n"
            f"Your mission is to guide the farmer based strictly on the following factual ground-truth field dossier.\n\n"
            f"=== FIELD GROUND-TRUTH DOSSIER ===\n"
            f"{dossier}\n"
            f"=== END OF DOSSIER ===\n\n"
            f"STRICT INSTRUCTIONS:\n"
            f"1. Language Requirement: You MUST reply entirely in {lang_label} ({lang_native}, code: {lang}). Use polite, warm, respectful rural farmer greetings.\n"
            f"2. Strict Grounding: Use ONLY facts, dates, precipitation millimeters, and NDVI metrics from the dossier. Never invent ungrounded data. If information is unavailable in the dossier, say so honestly.\n"
            f"3. Practical Agronomic Explanations:\n"
            f"   - Explain NDVI simply as crop greenness / foliage health ('फसल का हरापन').\n"
            f"   - Explain ET₀ simply as moisture lost to sunlight and air ('धूप-हवा से नमी का उड़ना').\n"
            f"   - Explain net water balance simply as moisture gain/loss ('पानी का संतुलन').\n"
            f"4. Spray & Chemical Safety:\n"
            f"   - If imminent rain (>= 2 mm in 48h) or high winds/temperatures are forecast, explicitly WARN the farmer against spraying foliar chemicals to prevent rain wash-off and monetary waste.\n"
            f"   - NEVER prescribe unverified chemical dosages or cocktail mixes. Always suggest consulting the chemical packet label or local KVK officer for exact dosages.\n"
            f"5. Formatting: Keep responses practical, well-structured with bullet points, and easy to read on mobile."
        )

        try:
            with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS)) as client:
                contents: List[types.Content] = []
                for msg in messages:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg["content"])],
                        )
                    )
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        max_output_tokens=800,
                    ),
                )
                if response and response.text:
                    return response.text.strip()
        except Exception as exc:
            logger.warning("Gemini chat API failed, falling back to rule-based engine: %s", exc)

    # Fallback to rule-based engine
    safe_stats = stats or {}
    return generate_fallback_response(latest_query, safe_stats, lang=lang)
