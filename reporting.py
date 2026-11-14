"""Field advisory report export generator for CropScope."""

import json
from datetime import datetime, timezone

from agronomy import (
    compute_agro_climatic_summary,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_growth_stage_guidance,
    summarize_canopy_health,
)
from analysis import AnalysisOutcome
from models import SatelliteResult, WeatherResult


def generate_advisory_markdown(outcome: AnalysisOutcome, generated_at: datetime | None = None) -> str:
    """Generate a structured Markdown field advisory report."""
    now_utc = generated_at or datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    req = outcome.request
    area = req.area
    lat_center, lon_center = area.center

    lines = [
        "# CropScope — Field Advisory Report",
        "",
        f"**Report Generated:** {timestamp_str}",
        "",
        "## 1. Field & Crop Overview",
        "",
        f"- **Crop:** {req.crop}",
        f"- **Growth Stage:** {req.growth_stage} ({get_growth_stage_guidance(req.growth_stage)})",
        f"- **Analysis Area:** {area.formatted_area()}",
        f"- **Bounding Box:** South {area.south:.6f}°, West {area.west:.6f}°, North {area.north:.6f}°, East {area.east:.6f}°",
        f"- **Center Coordinates:** {lat_center:.5f}°, {lon_center:.5f}°",
        "",
    ]

    # Weather & Water Balance section
    lines.append("## 2. Seven-Day Agro-Climatic & Water Balance Forecast")
    lines.append("")
    weather_res = outcome.weather.result
    if isinstance(weather_res, WeatherResult):
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)
        source_label = "Saved cache" if outcome.weather.cached else "Live Open-Meteo API"
        lines.extend([
            f"- **Data Source:** {source_label} ({weather_res.source_url})",
            f"- **Forecast Timezone:** {weather_res.timezone}",
            f"- **Fetched:** {weather_res.fetched_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
            f"- **Total Forecast Rain:** {summary.total_rain_mm:.1f} mm",
            f"- **Total Reference ET₀:** {summary.total_et0_mm:.1f} mm",
            f"- **Net Atmospheric Water Balance (P − ET₀):** {summary.net_balance_mm:+.1f} mm ({summary.status_label})",
            f"- **Favorable Fieldwork Days:** {summary.favorable_days_count} of {len(summary.days)} days",
        ])
        windows = evaluate_operational_windows(weather_res)
        alerts = generate_weather_alerts(weather_res)
        lines.append(
            f"- **Field Operations Windows:** {len(windows.spraying_favorable_days)} spraying days, "
            f"{len(windows.machinery_accessible_days)} machinery access days, "
            f"{len(windows.scouting_recommended_days)} scouting days"
        )
        if alerts:
            lines.append("- **Operational Weather Alerts:**")
            for alert in alerts:
                lines.append(f"  - {alert.message}")
        lines.extend([
            "",
            "| Date | Rain (mm) | Max Temp (°C) | Ref ET₀ (mm) | Net (P − ET₀) | Fieldwork Window | Notes |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ])
        for row in summary.days:
            lines.append(
                f"| {row.day.isoformat()} | {row.rain_mm:.1f} | {row.max_temp_c:.1f} | "
                f"{row.et0_mm:.1f} | {row.net_balance_mm:+.1f} | {row.suitability} | {row.reason} |"
            )
        lines.append("")
    elif outcome.weather.error:
        lines.extend([
            f"*Weather data unavailable: {outcome.weather.error}*",
            "",
        ])
    else:
        lines.extend([
            "*Weather data not available for this run.*",
            "",
        ])

    # Satellite section
    lines.append("## 3. Sentinel-2 Satellite Vegetation Observation")
    lines.append("")
    sat_res = outcome.satellite.result
    if isinstance(sat_res, SatelliteResult):
        sat_source = "Saved cache" if outcome.satellite.cached else "Live STAC Earth Search"
        platform = getattr(sat_res, "platform", None)
        sun_elevation = getattr(sat_res, "sun_elevation", None)
        sun_azimuth = getattr(sat_res, "sun_azimuth", None)
        mgrs_tile = getattr(sat_res, "mgrs_tile", None)
        true_color_png = getattr(sat_res, "true_color_png", None)
        mean_savi = getattr(sat_res, "mean_savi", None)
        canopy_zones = getattr(sat_res, "canopy_zones", None)

        platform_info = f" ({platform})" if platform else ""
        lines.extend([
            f"- **Data Source:** {sat_source}{platform_info} ([Scene {sat_res.scene_id}]({sat_res.catalog_url}))",
            f"- **Acquisition Date:** {sat_res.acquired_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
            f"- **Scene Cloud Cover:** {sat_res.scene_cloud_percent:.1f}%",
            f"- **Usable Pixels in Rectangle:** {sat_res.valid_pixel_percent:.1f}%",
            f"- **Image Dimensions:** {sat_res.width} × {sat_res.height} pixels (10 m native band)",
        ])
        if sun_elevation is not None and sun_azimuth is not None:
            lines.append(f"- **Solar Angles:** Elevation {sun_elevation:.1f}° · Azimuth {sun_azimuth:.1f}°")
        if mgrs_tile:
            lines.append(f"- **MGRS Tile:** {mgrs_tile}")
        if true_color_png is not None:
            lines.append("- **Optical Imagery:** Actual Sentinel-2 True Color Image (TCI 10 m sRGB) available")
        if sat_res.quality_message:
            lines.append(f"- **Quality Notice:** {sat_res.quality_message}")
        else:
            lines.extend([
                f"- **Mean NDVI:** {sat_res.mean_ndvi:.3f}",
                f"- **Median NDVI:** {sat_res.median_ndvi:.3f}",
            ])
            if mean_savi is not None:
                lines.append(f"- **Mean SAVI (Soil-Adjusted):** {mean_savi:.3f}")
            if canopy_zones:
                lines.append("- **Canopy Distribution Zones:**")
                for zone_name, pct in canopy_zones.items():
                    lines.append(f"  - {zone_name}: {pct:.1f}%")
                canopy_summary = summarize_canopy_health(canopy_zones)
                if canopy_summary:
                    lines.append(f"- **Canopy Summary:** {canopy_summary}")
        lines.append("")
    elif outcome.satellite.error:
        lines.extend([
            f"*Satellite data unavailable: {outcome.satellite.error}*",
            "",
        ])
    else:
        lines.extend([
            "*Satellite data not available for this run.*",
            "",
        ])

    # Recommendations section
    lines.append("## 4. Prioritized Field Checks & Management Considerations")
    lines.append("")
    if outcome.suggestions:
        lines.append(f"*{outcome.suggestion_source}*")
        lines.append("")
        for idx, item in enumerate(outcome.suggestions, 1):
            lines.append(f"### {idx}. {item.candidate.title}")
            lines.append(f"{item.candidate.action}")
            evidence_str = " ".join(piece.text for piece in item.evidence)
            lines.append(f"> **Evidence:** {evidence_str}")
            lines.append("")
    else:
        lines.append("*No supported management suggestions available from current data.*")
        lines.append("")

    # Limitations & Disclaimers
    lines.extend([
        "## 5. Decision-Support Boundaries & Disclaimers",
        "",
        "- **Decision Support Only:** CropScope provides advisory support, not automated agronomy or irrigation actuation.",
        "- **Atmospheric Estimates vs. Soil Measurements:** Precipitation is a gridded forecast from Open-Meteo, and ET₀ describes reference grass evapotranspiration. They do not constitute in-situ soil moisture sensor readings.",
        "- **Vegetation Greenness:** Sentinel-2 NDVI measures spectral greenness; it does not identify crop diseases, certify crop variety, or predict yields.",
        "- **Field Boundaries:** The analysis geometry is a user-defined rectangle and may encompass non-cropped borders or mixed land.",
        "- **Ground Verification:** Always verify field soil moisture, crop stage, and disease pressure on site before making financial or agronomic interventions.",
        "",
        "---",
        "*Report generated by CropScope — Open-source Precision Farming Decision Support*",
        "",
    ])

    return "\n".join(lines)


def generate_advisory_json(outcome: AnalysisOutcome, generated_at: datetime | None = None) -> str:
    """Generate a structured JSON export of the complete analysis."""
    now_utc = generated_at or datetime.now(timezone.utc)
    area = outcome.request.area
    weather_res = outcome.weather.result
    sat_res = outcome.satellite.result

    data = {
        "report_generated_utc": now_utc.isoformat(),
        "crop": outcome.request.crop,
        "growth_stage": outcome.request.growth_stage,
        "growth_stage_guidance": get_growth_stage_guidance(outcome.request.growth_stage),
        "area": {
            "south": area.south,
            "west": area.west,
            "north": area.north,
            "east": area.east,
            "center": list(area.center),
            "area_km2": area.area_km2,
            "area_ha": round(area.area_ha, 3),
            "area_acres": round(area.area_acres, 3),
        },
        "weather": None,
        "satellite": None,
        "suggestions": [
            {
                "id": s.candidate.id,
                "title": s.candidate.title,
                "action": s.candidate.action,
                "evidence": [e.text for e in s.evidence],
            }
            for s in outcome.suggestions
        ],
        "suggestion_source": outcome.suggestion_source,
    }

    if isinstance(weather_res, WeatherResult):
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)
        alerts = generate_weather_alerts(weather_res)
        data["weather"] = {
            "cached": outcome.weather.cached,
            "timezone": weather_res.timezone,
            "fetched_at_utc": weather_res.fetched_at_utc.isoformat(),
            "source_url": weather_res.source_url,
            "total_rain_mm": summary.total_rain_mm,
            "total_et0_mm": summary.total_et0_mm,
            "net_balance_mm": summary.net_balance_mm,
            "water_status": summary.status_label,
            "favorable_days_count": summary.favorable_days_count,
            "operational_windows": {
                "spraying_days": [d.isoformat() for d in windows.spraying_favorable_days],
                "machinery_days": [d.isoformat() for d in windows.machinery_accessible_days],
                "scouting_days": [d.isoformat() for d in windows.scouting_recommended_days],
            },
            "alerts": [
                {
                    "level": a.level,
                    "category": a.category,
                    "message": a.message,
                }
                for a in alerts
            ],
            "days": [
                {
                    "date": d.day.isoformat(),
                    "rain_mm": d.rain_mm,
                    "max_temp_c": d.max_temp_c,
                    "et0_mm": d.et0_mm,
                    "net_balance_mm": d.net_balance_mm,
                    "suitability": d.suitability,
                    "reason": d.reason,
                }
                for d in summary.days
            ],
        }

    if isinstance(sat_res, SatelliteResult):
        data["satellite"] = {
            "cached": outcome.satellite.cached,
            "scene_id": sat_res.scene_id,
            "acquired_at_utc": sat_res.acquired_at_utc.isoformat(),
            "cloud_cover_percent": sat_res.scene_cloud_percent,
            "usable_pixel_percent": sat_res.valid_pixel_percent,
            "mean_ndvi": sat_res.mean_ndvi,
            "median_ndvi": sat_res.median_ndvi,
            "mean_savi": getattr(sat_res, "mean_savi", None),
            "canopy_zones": getattr(sat_res, "canopy_zones", None),
            "quality_message": sat_res.quality_message,
            "has_true_color_image": getattr(sat_res, "true_color_png", None) is not None,
            "platform": getattr(sat_res, "platform", None),
            "sun_elevation": getattr(sat_res, "sun_elevation", None),
            "sun_azimuth": getattr(sat_res, "sun_azimuth", None),
            "mgrs_tile": getattr(sat_res, "mgrs_tile", None),
        }

    return json.dumps(data, indent=2)


def advisory_filename_base(outcome: AnalysisOutcome) -> str:
    """Generate a sanitized, cross-platform filename base for advisory exports."""
    import re
    raw_crop = outcome.request.crop.lower() if outcome.request.crop else "field"
    crop_slug = re.sub(r"[^\w\-]+", "_", raw_crop).strip("_") or "field"
    center = outcome.request.area.center
    return f"cropscope_advisory_{crop_slug}_{center[0]:.2f}_{center[1]:.2f}"


