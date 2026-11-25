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
    compute_crop_water_plan,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_growth_stage_guidance,
    summarize_canopy_health,
)
from analysis import AnalysisOutcome
from i18n import SUPPORTED_LANGUAGES, t
from models import SatelliteResult, WeatherResult
from satellite import summarize_scouting_hotspot

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_TIMEOUT_MS = 25_000


def get_dossier_summary_stats(
    outcome: AnalysisOutcome,
    historical_trend: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
        "min_temp_7d_c": None,
        "max_wind_7d_kmh": None,
        "avg_humidity_7d_pct": None,
        "total_gdd_base10": None,
        "crop_kc": None,
        "total_etc_7d_mm": None,
        "crop_net_balance_mm": None,
        "estimated_deficit_m3": None,
        "estimated_deficit_liters_per_acre": None,
        "mean_ndvi": None,
        "mean_savi": None,
        "uniformity_score_pct": None,
        "scouting_hotspot": "",
        "quadrant_stats": {},
        "cloud_cover_pct": None,
        "valid_pixels_pct": None,
        "canopy_summary": "",
        "canopy_zones": {},
        "suggestions_count": len(outcome.suggestions),
        "historical_scan_count": 0,
        "historical_ndvi_delta": None,
        "historical_ndvi_direction": None,
        "historical_prev_date": None,
    }
    if historical_trend:
        stats["historical_scan_count"] = historical_trend.get("scan_count", 0)
        stats["historical_ndvi_delta"] = historical_trend.get("ndvi_delta")
        stats["historical_ndvi_direction"] = historical_trend.get("ndvi_direction")
        stats["historical_prev_date"] = historical_trend.get("prev_scanned_at")

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
        stats["min_temp_7d_c"] = summary.min_temp_c
        stats["max_wind_7d_kmh"] = summary.max_wind_kmh
        stats["avg_humidity_7d_pct"] = summary.avg_humidity_pct
        stats["total_gdd_base10"] = summary.total_gdd_base10

        crop_plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
        stats["crop_kc"] = crop_plan.kc
        stats["total_etc_7d_mm"] = crop_plan.total_etc_mm
        stats["crop_net_balance_mm"] = crop_plan.crop_net_balance_mm
        stats["estimated_deficit_m3"] = crop_plan.deficit_m3
        stats["estimated_deficit_liters_per_acre"] = crop_plan.deficit_liters_per_acre

        # 48h rain & wind outlook (first 2 forecast days)
        first_48h_days = weather_res.days[:2]
        rain_48h = sum(d.rain_mm for d in first_48h_days)
        stats["imminent_rain_48h_mm"] = round(rain_48h, 2)
        # Unsafe to spray if imminent rain >= 2.0 mm, max temp >= 35°C, or wind >= 15 km/h
        stats["safe_to_spray_next_48h"] = (
            rain_48h < 2.0
            and all(d.max_temp_c < 35.0 for d in first_48h_days)
            and all(d.wind_speed_max_kmh is None or d.wind_speed_max_kmh < 15.0 for d in first_48h_days)
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
        stats["uniformity_score_pct"] = getattr(sat_res, "uniformity_score_pct", None)
        stats["quadrant_stats"] = getattr(sat_res, "quadrant_stats", None) or {}
        stats["scouting_hotspot"] = summarize_scouting_hotspot(
            stats["quadrant_stats"] or None,
            stats["uniformity_score_pct"],
        )
        stats["cloud_cover_pct"] = sat_res.scene_cloud_percent
        stats["valid_pixels_pct"] = sat_res.valid_pixel_percent
        stats["canopy_zones"] = sat_res.canopy_zones or {}
        stats["canopy_summary"] = summarize_canopy_health(sat_res.canopy_zones)

    return stats


def build_farmer_dossier(
    outcome: AnalysisOutcome,
    lang: str = "en",
    historical_trend: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a comprehensive, grounded field intelligence dossier for LLM context.

    This acts as the hyper-local ground-truth document for RAG generation, preventing
    hallucination and grounding all advice in this exact field's satellite pass and weather.
    """
    stats = get_dossier_summary_stats(outcome, historical_trend=historical_trend)
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
            f"- Crop-Adjusted Water Demand (ETc, Kc={stats['crop_kc']:.2f} for {req.crop} · {req.growth_stage}): {stats['total_etc_7d_mm']:.1f} mm (Net P − ETc: {stats['crop_net_balance_mm']:+.1f} mm; est. field gap {stats['estimated_deficit_m3']:,.1f} m³ or {stats['estimated_deficit_liters_per_acre']:,.0f} L/acre — atmospheric estimate, verify soil moisture on site)",
            f"- Imminent 48-Hour Rain Forecast: {stats['imminent_rain_48h_mm']:.1f} mm",
            f"- Spray Safety Window Next 48h: {'FAVORABLE' if stats['safe_to_spray_next_48h'] else 'UNFAVORABLE / CAUTION (risk of rain wash-off or heat)'}",
            f"- Peak Rain Day: {stats['peak_rain_day']} with {stats['peak_rain_mm']:.1f} mm rain",
            f"- Favorable Fieldwork Days: {summary.favorable_days_count} of {len(summary.days)} days",
            f"- Spraying Suitable Dates: {', '.join(str(d) for d in windows.spraying_favorable_days) if windows.spraying_favorable_days else 'None in 7-day forecast'}",
            f"- Machinery Accessible Dates: {', '.join(str(d) for d in windows.machinery_accessible_days) if windows.machinery_accessible_days else 'None'}",
        ])
        if summary.min_temp_c is not None:
            lines.append(f"- 7-Day Lowest Min Temperature: {summary.min_temp_c:.1f}°C")
        if summary.max_wind_kmh is not None:
            lines.append(f"- 7-Day Peak Wind Speed: {summary.max_wind_kmh:.1f} km/h")
        if summary.avg_humidity_pct is not None:
            lines.append(f"- 7-Day Mean Relative Humidity: {summary.avg_humidity_pct:.1f}%")
        if summary.total_gdd_base10 is not None:
            lines.append(f"- 7-Day Growing Degree Days (Base 10°C): {summary.total_gdd_base10:.1f} °C·d")
        has_min = any(d.min_temp_c is not None for d in summary.days)
        has_wind = any(d.wind_speed_max_kmh is not None for d in summary.days)
        has_prob = any(d.rain_probability_pct is not None for d in summary.days)
        has_hum = any(d.humidity_mean_pct is not None for d in summary.days)
        hdr = ["Date", "Max Temp (°C)"]
        sep = [":---", ":---:"]
        if has_min:
            hdr.append("Min Temp (°C)")
            sep.append(":---:")
        if has_wind:
            hdr.append("Wind (km/h)")
            sep.append(":---:")
        if has_prob:
            hdr.append("Rain Prob (%)")
            sep.append(":---:")
        if has_hum:
            hdr.append("Humidity (%)")
            sep.append(":---:")
        hdr.extend(["Rain (mm)", "ET₀ (mm)", "Net Balance (mm)", "Field Suitability", "Reason"])
        sep.extend([":---:", ":---:", ":---:", ":---:", ":---"])
        lines.extend([
            "",
            "### Daily Meteorological Breakdown:",
            "| " + " | ".join(hdr) + " |",
            "| " + " | ".join(sep) + " |",
        ])
        for d in summary.days:
            row_cells = [str(d.day), f"{d.max_temp_c:.1f}°C"]
            if has_min:
                row_cells.append(f"{d.min_temp_c:.1f}°C" if d.min_temp_c is not None else "—")
            if has_wind:
                row_cells.append(f"{d.wind_speed_max_kmh:.1f}" if d.wind_speed_max_kmh is not None else "—")
            if has_prob:
                row_cells.append(f"{d.rain_probability_pct:.0f}%" if d.rain_probability_pct is not None else "—")
            if has_hum:
                row_cells.append(f"{d.humidity_mean_pct:.0f}%" if d.humidity_mean_pct is not None else "—")
            row_cells.extend([f"{d.rain_mm:.1f} mm", f"{d.et0_mm:.1f} mm", f"{d.net_balance_mm:+.1f} mm", d.suitability, d.reason])
            lines.append("| " + " | ".join(row_cells) + " |")

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
        if stats["uniformity_score_pct"] is not None:
            lines.append(f"- Field Canopy Uniformity: {stats['uniformity_score_pct']:.1f}%")
        if stats["scouting_hotspot"]:
            lines.append(f"- Spatial Scouting Priority: {stats['scouting_hotspot']}")
        if stats["quadrant_stats"]:
            lines.append("")
            lines.append("### 4-Quadrant Spatial Vigor:")
            for q_name, q_vals in stats["quadrant_stats"].items():
                lines.append(
                    f"- {q_name}: Mean NDVI {q_vals['mean_ndvi']:.3f} ({q_vals['low_vigor_pct']:.1f}% sparse/bare)"
                )
        if stats.get("historical_ndvi_delta") is not None:
            lines.append(
                f"- Multi-Scan NDVI Progression: {stats['historical_ndvi_delta']:+.3f} ({stats['historical_ndvi_direction']}) compared to prior recorded scan on {stats['historical_prev_date']} ({stats['historical_scan_count']} scans recorded)"
            )
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


# ── Agronomic Domain Guardrails & Refusal Handlers ───────────────────────────

OFF_TOPIC_STRICT_PATTERNS = [
    # Computer science, programming & algorithms
    r"\blinked\s*list\b",
    r"\bbinary\s*tree\b",
    r"\bleetcode\b",
    r"\bcodeforces\b",
    r"\bhacker\s*rank\b",
    r"\b(write|give|create|generate|provide)\s+(a\s+)?(code|program|script|function|algorithm|class)\b",
    r"\b(python|java|c\+\+|javascript|typescript|golang|rust|html|css|sql)\s+(program|code|script|solution)\b",
    r"\b(reverse|sort|traverse|invert)\s+(the\s+|a\s+)?(linked\s*list|string|array|binary\s*tree)\b",
    r"\b(bubble|quick|merge|insertion|heap)\s*sort\b",
    r"\bfibonacci\s*(series|sequence|number)?\b",
    r"\b(time|space)\s+complexity\b",
    r"\b(लिंक्ड\s*लिस्ट|रिवर्स|प्रोग्राम|कोडिंग)\b",
    # Cinema & Entertainment
    r"\bjames\s*bond\b",
    r"\b(plot|story|ending|review|synopsis)\s+(of|for)\s+([a-z0-9\s]+\s+)?(movie|film|series|cinema|show)\b",
    r"\b(movie|film|cinema)\s+(plot|synopsis|storyline)\b",
    r"\bwho\s+acted\s+in\b",
    r"\b(जेम्स\s*बॉन्ड|फिल्म\s+की\s+कहानी|मूवी\s+की\s+कहानी)\b",
    # Video Games
    r"\b(video\s*game|playstation|xbox|minecraft|fortnite|gta|grand\s+theft\s+auto)\b",
    # Sports & General Politics/Finance
    r"\b(cricket\s+score|ipl\s+match|fifa\s+world\s*cup)\b",
    r"\b(bitcoin|cryptocurrency|crypto\s+wallet|ethereum)\b",
    r"\b(stock\s+market|day\s+trading|mutual\s+fund\s+portfolio)\b",
]

OFF_TOPIC_GENERAL_PATTERNS = [
    r"\b(movie|film|cinema|actor|actress|bollywood|hollywood|netflix)\b",
    r"\b(programming|coding|algorithm|data\s*structure)\b",
    r"\b(song\s+lyrics|tell\s+me\s+a\s+joke)\b",
    r"\b(फिल्म|मूवी|सिनेमा|गाना|क्रिकेट)\b",
]

AGRONOMIC_CONTEXT_TERMS = [
    "crop", "farm", "farmer", "field", "soil", "wheat", "paddy", "rice",
    "maize", "cotton", "mustard", "sugarcane", "potato", "tomato", "chilli",
    "onion", "canopy", "ndvi", "savi", "irrigation", "water", "rain",
    "weather", "pest", "disease", "spray", "pesticide", "fertilizer",
    "seed", "sowing", "harvest", "yield", "dossier", "khet", "fasal",
    "kisan", "barish", "mausam", "sinchai", "खेती", "फसल", "खेत",
    "मौसम", "बारिश", "खाद", "दवा", "स्प्रे", "सिंचाई", "बीज"
]


def is_off_topic_query(query: str) -> bool:
    """Detect if a user query is unambiguously non-agronomic / off-topic."""
    q = query.lower().strip()
    if not q:
        return False

    # Check strict off-topic patterns that never belong in field agronomy
    for pat in OFF_TOPIC_STRICT_PATTERNS:
        if re.search(pat, q):
            return True

    # Check general entertainment/coding patterns only if no agronomic context is present
    has_agronomic_context = any(term in q for term in AGRONOMIC_CONTEXT_TERMS)
    if not has_agronomic_context:
        for pat in OFF_TOPIC_GENERAL_PATTERNS:
            if re.search(pat, q):
                return True

    return False


def get_off_topic_refusal(lang: str = "en") -> str:
    """Return a polite, localized domain refusal message redirecting to agronomy."""
    refusals = {
        "hi": (
            "🌾 **किसान मित्र केवल कृषि एवं फसल सलाहकार है:**\n\n"
            "मैं एक समर्पित डिजिटल कृषि सलाहकार (Krishi Vigyan Kendra / CropScope AI) हूँ। "
            "मैं केवल आपकी फसल, मिट्टी, मौसम पूर्वानुमान, कीटनाशक/खाद छिड़काव और सैटेलाइट निगरानी से संबंधित प्रश्नों के उत्तर दे सकता हूँ।\n\n"
            "⚠️ मैं फिल्मों, सॉफ्टवेयर प्रोग्रामिंग या गैर-कृषि विषयों पर सहायता करने में असमर्थ हूँ।\n\n"
            "💡 *कृपया अपनी फसल (जैसे गेहूं, धान), आगामी मौसम, या खेत प्रबंधन के बारे में पूछें!*"
        ),
        "pa": (
            "🌾 **ਕਿਸਾਨ ਮਿੱਤਰ ਖੇਤੀਬਾੜੀ ਸਲਾਹਕਾਰ:**\n\n"
            "ਮੈਂ ਸਿਰਫ਼ ਖੇਤੀਬਾੜੀ ਅਤੇ ਫ਼ਸਲ ਪ੍ਰਬੰਧਨ (ਮੌਸਮ, ਸਿੰਚਾਈ, ਸਪਰੇਅ ਅਤੇ ਸੈਟੇਲਾਈਟ ਰਿਪੋਰਟ) ਲਈ ਇੱਕ ਵਿਸ਼ੇਸ਼ ਡਿਜੀਟਲ ਸਹਾਇਕ ਹਾਂ। "
            "ਮੈਂ ਫ਼ਿਲਮਾਂ, ਕੰਪਿਊਟਰ ਕੋਡਿੰਗ ਜਾਂ ਗੈਰ-ਖੇਤੀਬਾੜੀ ਵਿਸ਼ਿਆਂ ਸੰਬੰਧੀ ਜਾਣਕਾਰੀ ਨਹੀਂ ਦੇ ਸਕਦਾ।\n\n"
            "💡 *ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ ਫ਼ਸਲ, ਮੌਸਮ ਜਾਂ ਖੇਤ ਸੰਬੰਧੀ ਕੋਈ ਵੀ ਸਵਾਲ ਪੁੱਛੋ!*"
        ),
        "mr": (
            "🌾 **किसान मित्र कृषी सल्लागार:**\n\n"
            "मी केवळ शेती, पीक व्यवस्थापन, हवामान अंदाज, सिंचन आणि उपग्रह निरीक्षणासाठी समर्पित कृषी सल्लागार आहे. "
            "मी चित्रपट, संगणक कोडिंग किंवा इतर गैर-कृषी विषयांवर मार्गदर्शन करू शकत नाही.\n\n"
            "💡 *कृपया आपल्या शेतातील पिके किंवा हवामानाबद्दल प्रश्न विचारा!*"
        ),
        "te": (
            "🌾 **కిసాన్ మిత్ర వ్యవసాయ సలహాదారు:**\n\n"
            "నేను వ్యవసాయం, పంట యాజమాన్యం, వాతావరణ సమాచారం మరియు ఉపగ్రహ పర్యవేక్షణకు మాత్రమే సహాయపడగలను. "
            "సినిమాలు, కంప్యూటర్ ప్రోగ్రామింగ్ వంటి ఇతర అంశాలపై నేను సమాధానం ఇవ్వలేను.\n\n"
            "💡 *దయచేసి మీ పంట లేదా వ్యవసాయ పనుల గురించి అడగండి!*"
        ),
        "ta": (
            "🌾 **கிசான் மித்ரா விவசாய ஆலோசகர்:**\n\n"
            "நான் விவசாயம், பயிர் மேலாண்மை, வானிலை மற்றும் செயற்கைக்கோள் கண்காணிப்புக்கான பிரத்யேக ஆலோசகர். "
            "திரைப்படங்கள், கணினி புரோகிராமிங் போன்ற விவசாயம் அல்லாத தலைப்புகளில் என்னால் பதிலளிக்க முடியாது.\n\n"
            "💡 *தயவுசெய்து உங்கள் பயிர் அல்லது விவசாயம் சார்ந்த கேள்விகளைக் கேளுங்கள்!*"
        ),
        "gu": (
            "🌾 **કિસાન મિત્ર કૃષિ સલાહકાર:**\n\n"
            "હું ફક્ત ખેતી, પાક વ્યવસ્થાપન, હવામાન અને સેટેલાઇટ રિપોર્ટ માટે સમર્પિત ડિજિટલ સલાહકાર છું. "
            "હું ફિલ્મો, કોડિંગ અથવા બિન-કૃષિ વિષયો પર માહિતી આપી શકતો નથી.\n\n"
            "💡 *કૃપા કરીને તમારા પાક અથવા ખેત સંબંધી પ્રશ્ન પૂછો!*"
        ),
        "bn": (
            "🌾 **কিষাণ মিত্র কৃষি উপদেষ্টা:**\n\n"
            "আমি শুধুমাত্র কৃষি, ফসলের যত্ন, আবহাওয়া এবং স্যাটেলাইট মনিটরিং সম্পর্কিত সহায়তার জন্য নিবেদিত। "
            "সিনেমা, কম্পিউটার কোডিং বা অ-কৃষি বিষয়ে আমি উত্তর দিতে অক্ষম।\n\n"
            "💡 *অনুগ্রহ করে আপনার ফসল বা কৃষি সংক্রান্ত প্রশ্ন জিজ্ঞাসা করুন!*"
        ),
        "kn": (
            "🌾 **ಕಿಸಾನ್ ಮಿತ್ರ ಕೃಷಿ ಸಲಹೆಗಾರ:**\n\n"
            "ನಾನು ಕೃಷಿ, ಬೆಳೆ ನಿರ್ವಹಣೆ, ಹವಾಮಾನ ಮತ್ತು ಉಪಗ್ರಹ ವೀಕ್ಷಣೆಗೆ ಮಾತ್ರ ಮೀಸಲಾದ ಡಿಜಿಟಲ್ ಸಲಹೆಗಾರ. "
            "ಸಿನಿಮಾ, ಪ್ರೋಗ್ರಾಮಿಂಗ್ ಅಥವಾ ಕೃಷಿಯೇತರ ವಿಷಯಗಳಿಗೆ ನಾನು ಉತ್ತರಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.\n\n"
            "💡 *ದಯವಿಟ್ಟು ನಿಮ್ಮ ಬೆಳೆ ಅಥವಾ ಕೃಷಿ ಸಂಬಂಧಿತ ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಿ!*"
        ),
        "ml": (
            "🌾 **കിസാൻ മിത്ര കാർഷിക ഉപദേശകൻ:**\n\n"
            "ഞാൻ കൃഷി, വിള പരിപാലനം, കാലാവസ്ഥ എന്നിവയിൽ സഹായിക്കാൻ മാത്രമുള്ള കാർഷിക സഹായിയാണ്. "
            "സിനിമകൾ, കമ്പ്യൂട്ടർ കോഡിംഗ് തുടങ്ങിയ കാർഷികേതര വിഷയങ്ങളിൽ എനിക്ക് മറുപടി നൽകാൻ കഴിയില്ല.\n\n"
            "💡 *ദയവായി നിങ്ങളുടെ വിള അല്ലെങ്കിൽ കൃഷിയെക്കുറിച്ചുള്ള ചോദ്യങ്ങൾ ചോദിക്കുക!*"
        ),
    }

    return refusals.get(
        lang,
        (
            "🌾 **Kisan Mitra Agronomic Domain Scope:**\n\n"
            "I am specialized exclusively as an agricultural and precision-farming field advisor (Krishi Vigyan Kendra / CropScope AI). "
            "I can only assist with crop health, soil moisture balance, weather forecasts, spray planning, and satellite vegetation monitoring for your farm.\n\n"
            "⚠️ I cannot answer questions about movies, entertainment, software programming, or other non-agricultural topics.\n\n"
            "💡 *Please feel free to ask about your crop management, spraying windows, or local weather forecast!*"
        ),
    )


EASTER_EGG_TRIGGERS = (
    "easter egg",
    "easteregg",
    "jai kisan",
    "jai jawan jai kisan",
    "जय जवान जय किसान",
    "जय किसान",
    "who made cropscope",
    "who created cropscope",
    "who built cropscope",
    "cropscope secret",
    "konami",
    "mars",
    "flight deck",
    "matrix",
    "isro",
    "orbital",
)


def is_easter_egg_query(query: str) -> bool:
    """Check if query triggers the secret CropScope tribute easter egg."""
    if not query or not query.strip():
        return False
    q = query.lower().strip()
    return any(trig in q for trig in EASTER_EGG_TRIGGERS)


def get_easter_egg_response(lang: str = "en") -> str:
    """Return celebratory tribute easter egg response for Indian farmers & creators."""
    return (
        "🌾 **जय जवान, जय किसान! (Hail the Soldier, Hail the Farmer!)** 🚜💚\n\n"
        "🎉 **You unlocked the secret CropScope Easter Egg & Orbital Channel!** 🛰️✨\n\n"
        "CropScope was engineered with deep respect for Indian farmers — combining ESA Sentinel-2 "
        "satellite constellations, Open-Meteo precision agro-meteorology, and grounded AI to bring "
        "space-age precision agronomy directly to the soil.\n\n"
        "🕹️ **CLASSIFIED ORBITAL FLIGHT DECK HUD:**\n"
        "- **Tap the 🛰️ satellite icon** in the top header 3 times (or press the classic Konami Code `↑ ↑ ↓ ↓ ← → ← → B A` on your keyboard) to open the **Retro Sci-Fi Orbital Flight Deck & Radar**!\n"
        "- From there, you can warp to the **Mars Sol 54 Potato Farm (Acidalia Planitia)** or toggle **Matrix Cyber-Rain**!\n\n"
        "— *Crafted with ❤️ for India's Annadatas (अन्नदाता) by Shreyash Shukla & Team* 🇮🇳"
    )


def generate_fallback_response(
    query: str,
    stats: Dict[str, Any],
    lang: str = "en",
) -> str:
    """Generate a reliable, grounded rule-based advisory response when LLM is unavailable."""
    if is_easter_egg_query(query):
        return get_easter_egg_response(lang=lang)

    if is_off_topic_query(query):
        return get_off_topic_refusal(lang=lang)

    q_lower = query.lower()
    crop = stats.get("crop") or "Crop"
    rain_7d = stats.get("total_rain_7d_mm", 0.0)
    rain_48h = stats.get("imminent_rain_48h_mm", 0.0)
    peak_day = stats.get("peak_rain_day") or "upcoming days"
    peak_mm = stats.get("peak_rain_mm", 0.0)
    safe_spray = stats.get("safe_to_spray_next_48h", True)
    max_wind = stats.get("max_wind_7d_kmh")
    min_temp = stats.get("min_temp_7d_c")
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
            wind_note_hi = f" (तेज हवा {max_wind:.1f} किमी/घंटा भी अनुमानित है)" if (max_wind is not None and max_wind >= 15.0) else ""
            wind_note_pa = f" (ਤੇਜ਼ ਹਵਾ {max_wind:.1f} ਕਿਮੀ/ਘੰਟਾ ਦੀ ਵੀ ਸੰਭਾਵਨਾ ਹੈ)" if (max_wind is not None and max_wind >= 15.0) else ""
            wind_note_en = f", wind up to {max_wind:.1f} km/h," if (max_wind is not None and max_wind >= 15.0) else ""
            if lang == "hi":
                return (
                    f"🚜 **छिड़काव (Spray) चेतावनी:**\n\n"
                    f"⚠️ **सावधानी: अगले 48 घंटों में कीटनाशक या खाद का छिड़काव टालें!**\n"
                    f"- अगले 48 घंटों में **{rain_48h:.1f} मिमी** बारिश{wind_note_hi} का अनुमान है।\n"
                    f"- बारिश या तेज हवा से छिड़की गई दवा बह/उड़ जाएगी, जिससे फसल को लाभ नहीं मिलेगा और पैसे का नुकसान होगा।\n"
                    f"- शांत और सूखे मौसम में ही छिड़काव की योजना बनाएं।"
                )
            elif lang == "pa":
                return (
                    f"🚜 **ਸਪਰੇਅ ਚੇਤਾਵਨੀ:**\n\n"
                    f"⚠️ **ਸਾਵਧਾਨੀ: ਅਗਲੇ 48 ਘੰਟਿਆਂ 'ਚ ਸਪਰੇਅ ਨਾ ਕਰੋ!**\n"
                    f"- ਆਉਣ ਵਾਲੇ 48 ਘੰਟਿਆਂ 'ਚ **{rain_48h:.1f} ਮਿਮੀ** ਮੀਂਹ{wind_note_pa} ਪੈ ਸਕਦਾ ਹੈ।\n"
                    f"- ਮੀਂਹ ਜਾਂ ਤੇਜ਼ ਹਵਾ ਕਾਰਨ ਦਵਾਈ ਦਾ ਅਸਰ ਘਟ ਜਾਵੇਗਾ ਅਤੇ ਖਰਚਾ ਵਿਅਰਥ ਜਾਵੇਗਾ।"
                )
            else:
                return (
                    f"🚜 **Spraying Warning for {crop}:**\n\n"
                    f"⚠️ **UNFAVORABLE: Hold chemical spraying for the next 48 hours.**\n"
                    f"- Forecast rain ({rain_48h:.1f} mm){wind_note_en} or high thermal stress poses a serious risk of foliar wash-off, drift, or droplet volatilization.\n"
                    f"- Postpone application until calm, dry conditions return."
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
        etc_7d = stats.get("total_etc_7d_mm")
        crop_kc = stats.get("crop_kc")
        crop_net = stats.get("crop_net_balance_mm")
        l_per_ac = stats.get("estimated_deficit_liters_per_acre")
        if lang == "hi":
            etc_line = (
                f"- फसल की अनुमानित पानी की मांग (ETc, Kc={crop_kc:.2f}): **{etc_7d:.1f} मिमी** (अंतर: **{crop_net:+.1f} मिमी**, ~**{l_per_ac:,.0f} लीटर/एकड़** कमी)।\n"
                if etc_7d is not None and crop_kc is not None and crop_net is not None and l_per_ac is not None
                else ""
            )
            return (
                f"💧 **जल संतुलन व सिंचाई सलाह ({crop}):**\n\n"
                f"- 7 दिनों में संभावित वर्षा: **{rain_7d:.1f} मिमी**।\n"
                f"- धूप व हवा से नमी हानि (ET₀): **{stats.get('total_et0_7d_mm', 0.0):.1f} मिमी**।\n"
                f"{etc_line}"
                f"- शुद्ध जल संतुलन (वर्षा − नमी हानि): **{net_bal:+.1f} मिमी** ({stats.get('water_balance_status', '')})।\n\n"
                f"💡 *सलाह:* {'मिट्टी में नमी की जांच करें; यदि ऊपरी मिट्टी सूखी हो तो हल्की सिंचाई की योजना बनाएं।' if (crop_net if crop_net is not None else net_bal) < -10 else 'वर्षा से पर्याप्त नमी या संतुलित स्थिति है, सिंचाई से पहले खेत की मिट्टी जांच लें।'}"
            )
        else:
            etc_line = (
                f"- Crop-adjusted water demand (ETc, Kc={crop_kc:.2f}): **{etc_7d:.1f} mm** (crop net P − ETc: **{crop_net:+.1f} mm**, ~**{l_per_ac:,.0f} L/acre** gap).\n"
                if etc_7d is not None and crop_kc is not None and crop_net is not None and l_per_ac is not None
                else ""
            )
            return (
                f"💧 **Agro-Climatic Water Balance & Irrigation ({crop}):**\n\n"
                f"- Cumulative 7-day rainfall: **{rain_7d:.1f} mm**.\n"
                f"- Reference evapotranspiration (ET₀): **{stats.get('total_et0_7d_mm', 0.0):.1f} mm**.\n"
                f"{etc_line}"
                f"- Net atmospheric water balance (P − ET₀): **{net_bal:+.1f} mm** ({stats.get('water_balance_status', '')}).\n\n"
                f"💡 *Recommendation:* {'Moisture deficit trend; check topsoil moisture on site before scheduling irrigation.' if (crop_net if crop_net is not None else net_bal) < -10 else 'Moisture accumulation or near-balanced outlook; verify root-zone moisture before irrigating.'}"
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

    # Secret tribute easter egg
    if is_easter_egg_query(latest_query):
        return get_easter_egg_response(lang=lang)

    # Strict domain guardrail: refuse off-topic requests immediately
    if is_off_topic_query(latest_query):
        return get_off_topic_refusal(lang=lang)

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
            f"1. Strict Domain Scope & Guardrails (CRITICAL):\n"
            f"   - You are EXCLUSIVELY an agricultural and precision-farming field advisor.\n"
            f"   - You MUST REFUSE any questions or requests unrelated to agriculture, farming, crops, soil, agro-weather, irrigation, pesticides/fertilizers, or the provided field dossier.\n"
            f"   - If the user asks about movies/entertainment (e.g. plot of James Bond or other films), computer programming/coding/algorithms (e.g. reversing a linked list, writing code), creative fiction, sports, politics, general trivia, or any non-farming topic, you MUST POLITELY DECLINE.\n"
            f"   - When declining, explain warmly in {lang_label} ({lang_native}) that you are Kisan Mitra, dedicated solely to farm advisory and field operations, and invite them to ask about their crops, soil, weather, or satellite canopy health instead.\n"
            f"   - NEVER fulfill off-topic requests under any circumstances.\n"
            f"2. Language Requirement: You MUST reply entirely in {lang_label} ({lang_native}, code: {lang}). Use polite, warm, respectful rural farmer greetings.\n"
            f"3. Strict Grounding: Use ONLY facts, dates, precipitation millimeters, and NDVI metrics from the dossier. Never invent ungrounded data. If information is unavailable in the dossier, say so honestly.\n"
            f"4. Practical Agronomic Explanations:\n"
            f"   - Explain NDVI simply as crop greenness / foliage health ('फसल का हरापन').\n"
            f"   - Explain ET₀ simply as moisture lost to sunlight and air ('धूप-हवा से नमी का उड़ना').\n"
            f"   - Explain net water balance simply as moisture gain/loss ('पानी का संतुलन').\n"
            f"5. Spray & Chemical Safety:\n"
            f"   - If imminent rain (>= 2 mm in 48h) or high winds/temperatures are forecast, explicitly WARN the farmer against spraying foliar chemicals to prevent rain wash-off and monetary waste.\n"
            f"   - NEVER prescribe unverified chemical dosages or cocktail mixes. Always suggest consulting the chemical packet label or local KVK officer for exact dosages.\n"
            f"6. Formatting: Keep responses practical, well-structured with bullet points, and easy to read on mobile."
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
