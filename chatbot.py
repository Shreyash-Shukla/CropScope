"""CropScope Kisan Mitra (किसान मित्र) Grounded RAG Chatbot Engine.

Provides hyper-local, grounded agricultural intelligence and multilingual chat
support for Indian farmers, using real-time satellite canopy analytics and 7-day
agro-climatic water balance forecasts.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
