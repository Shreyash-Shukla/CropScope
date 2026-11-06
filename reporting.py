"""Field advisory report export generator for CropScope."""

import json
from datetime import datetime, timezone

from agronomy import compute_agro_climatic_summary
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
        f"- **Growth Stage:** {req.growth_stage}",
        f"- **Analysis Area:** {area.area_km2:.3f} km²",
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
        source_label = "Saved cache" if outcome.weather.cached else "Live Open-Meteo API"
        lines.extend([
            f"- **Data Source:** {source_label} ({weather_res.source_url})",
            f"- **Forecast Timezone:** {weather_res.timezone}",
            f"- **Fetched:** {weather_res.fetched_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
            f"- **Total Forecast Rain:** {summary.total_rain_mm:.1f} mm",
            f"- **Total Reference ET₀:** {summary.total_et0_mm:.1f} mm",
            f"- **Net Atmospheric Water Balance (P − ET₀):** {summary.net_balance_mm:+.1f} mm ({summary.status_label})",
            f"- **Favorable Fieldwork Days:** {summary.favorable_days_count} of {len(summary.days)} days",
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
        lines.extend([
            f"- **Data Source:** {sat_source} ([Scene {sat_res.scene_id}]({sat_res.catalog_url}))",
            f"- **Acquisition Date:** {sat_res.acquired_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
            f"- **Scene Cloud Cover:** {sat_res.scene_cloud_percent:.1f}%",
            f"- **Usable Pixels in Rectangle:** {sat_res.valid_pixel_percent:.1f}%",
            f"- **Image Dimensions:** {sat_res.width} × {sat_res.height} pixels (10 m native band)",
        ])
        if sat_res.quality_message:
            lines.append(f"- **Quality Notice:** {sat_res.quality_message}")
        else:
            lines.extend([
                f"- **Mean NDVI:** {sat_res.mean_ndvi:.3f}",
                f"- **Median NDVI:** {sat_res.median_ndvi:.3f}",
            ])
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
        "area": {
            "south": area.south,
            "west": area.west,
            "north": area.north,
            "east": area.east,
            "center": list(area.center),
            "area_km2": area.area_km2,
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
            "quality_message": sat_res.quality_message,
        }

    return json.dumps(data, indent=2)

