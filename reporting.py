"""Field advisory report export generator for CropScope."""

import base64
import html
import json
from datetime import datetime, timezone
from urllib.parse import quote

from agronomy import (
    compute_agro_climatic_summary,
    compute_crop_water_plan,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_growth_stage_guidance,
    summarize_canopy_health,
)
from analysis import AnalysisOutcome
from models import SatelliteResult, WeatherResult
from satellite import summarize_scouting_hotspot


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
        crop_plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
        source_label = "Saved cache" if outcome.weather.cached else "Live Open-Meteo API"
        lines.extend([
            f"- **Data Source:** {source_label} ({weather_res.source_url})",
            f"- **Forecast Timezone:** {weather_res.timezone}",
            f"- **Fetched:** {weather_res.fetched_at_utc.strftime('%Y-%m-%d %H:%M UTC')}",
            f"- **Total Forecast Rain:** {summary.total_rain_mm:.1f} mm",
            f"- **Total Reference ET₀:** {summary.total_et0_mm:.1f} mm",
            f"- **Net Atmospheric Water Balance (P − ET₀):** {summary.net_balance_mm:+.1f} mm ({summary.status_label})",
            f"- **Crop Water Demand (ETc, {crop_plan.kc_source}, Kc={crop_plan.kc:.2f}):** {crop_plan.total_etc_mm:.1f} mm (Net P − ETc: {crop_plan.crop_net_balance_mm:+.1f} mm · {crop_plan.status_label})",
            f"- **Estimated Field Deficit Volume:** {crop_plan.deficit_m3:,.1f} m³ total ({crop_plan.deficit_liters_per_acre:,.0f} L/acre across {crop_plan.field_area_acres:.2f} ac — verify soil moisture before irrigating)",
            f"- **Favorable Fieldwork Days:** {summary.favorable_days_count} of {len(summary.days)} days",
        ])
        if summary.min_temp_c is not None:
            lines.append(f"- **7-Day Lowest Min Temp:** {summary.min_temp_c:.1f} °C")
        if summary.max_wind_kmh is not None:
            lines.append(f"- **7-Day Peak Wind Speed:** {summary.max_wind_kmh:.1f} km/h")
        if summary.avg_humidity_pct is not None:
            lines.append(f"- **7-Day Mean Relative Humidity:** {summary.avg_humidity_pct:.1f}%")
        if summary.total_gdd_base10 is not None:
            lines.append(f"- **7-Day Growing Degree Days (GDD Base 10°C):** {summary.total_gdd_base10:.1f} °C·d")
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
        has_min = any(d.min_temp_c is not None for d in summary.days)
        has_wind = any(d.wind_speed_max_kmh is not None for d in summary.days)
        has_prob = any(d.rain_probability_pct is not None for d in summary.days)
        has_hum = any(d.humidity_mean_pct is not None for d in summary.days)
        header_cols = ["Date", "Rain (mm)", "Max Temp (°C)"]
        align_cols = ["---", "---:", "---:"]
        if has_min:
            header_cols.append("Min Temp (°C)")
            align_cols.append("---:")
        if has_wind:
            header_cols.append("Wind (km/h)")
            align_cols.append("---:")
        if has_prob:
            header_cols.append("Rain Prob (%)")
            align_cols.append("---:")
        if has_hum:
            header_cols.append("Humidity (%)")
            align_cols.append("---:")
        header_cols.extend(["Ref ET₀ (mm)", "Net (P − ET₀)", "Fieldwork Window", "Notes"])
        align_cols.extend(["---:", "---:", "---", "---"])
        lines.extend([
            "",
            "| " + " | ".join(header_cols) + " |",
            "| " + " | ".join(align_cols) + " |",
        ])
        for row in summary.days:
            cells = [row.day.isoformat(), f"{row.rain_mm:.1f}", f"{row.max_temp_c:.1f}"]
            if has_min:
                cells.append(f"{row.min_temp_c:.1f}" if row.min_temp_c is not None else "—")
            if has_wind:
                cells.append(f"{row.wind_speed_max_kmh:.1f}" if row.wind_speed_max_kmh is not None else "—")
            if has_prob:
                cells.append(f"{row.rain_probability_pct:.0f}" if row.rain_probability_pct is not None else "—")
            if has_hum:
                cells.append(f"{row.humidity_mean_pct:.0f}" if row.humidity_mean_pct is not None else "—")
            cells.extend([f"{row.et0_mm:.1f}", f"{row.net_balance_mm:+.1f}", row.suitability, row.reason])
            lines.append("| " + " | ".join(cells) + " |")
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
            uniformity = getattr(sat_res, "uniformity_score_pct", None)
            quadrant_stats = getattr(sat_res, "quadrant_stats", None)
            if uniformity is not None:
                lines.append(f"- **Field Canopy Uniformity:** {uniformity:.1f}%")
            if canopy_zones:
                lines.append("- **Canopy Distribution Zones:**")
                for zone_name, pct in canopy_zones.items():
                    lines.append(f"  - {zone_name}: {pct:.1f}%")
                canopy_summary = summarize_canopy_health(canopy_zones)
                if canopy_summary:
                    lines.append(f"- **Canopy Summary:** {canopy_summary}")
            if quadrant_stats:
                hotspot = summarize_scouting_hotspot(quadrant_stats, uniformity)
                if hotspot:
                    lines.append(f"- **Spatial Scouting Cue:** {hotspot}")
                lines.append("- **4-Quadrant Vigor Breakdown:**")
                for q_name, q_vals in quadrant_stats.items():
                    lines.append(
                        f"  - {q_name}: Mean NDVI {q_vals['mean_ndvi']:.3f} ({q_vals['low_vigor_pct']:.1f}% sparse/bare)"
                    )
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
        crop_plan = compute_crop_water_plan(weather_res, outcome.request.crop, outcome.request.growth_stage)
        data["weather"] = {
            "cached": outcome.weather.cached,
            "timezone": weather_res.timezone,
            "fetched_at_utc": weather_res.fetched_at_utc.isoformat(),
            "source_url": weather_res.source_url,
            "total_rain_mm": summary.total_rain_mm,
            "total_et0_mm": summary.total_et0_mm,
            "net_balance_mm": summary.net_balance_mm,
            "water_status": summary.status_label,
            "crop_water_plan": {
                "kc": crop_plan.kc,
                "kc_source": crop_plan.kc_source,
                "total_etc_mm": crop_plan.total_etc_mm,
                "crop_net_balance_mm": crop_plan.crop_net_balance_mm,
                "estimated_deficit_mm": crop_plan.estimated_deficit_mm,
                "deficit_m3": crop_plan.deficit_m3,
                "deficit_liters_per_acre": crop_plan.deficit_liters_per_acre,
                "status_label": crop_plan.status_label,
            },
            "favorable_days_count": summary.favorable_days_count,
            "min_temp_c": summary.min_temp_c,
            "max_wind_kmh": summary.max_wind_kmh,
            "avg_humidity_pct": summary.avg_humidity_pct,
            "total_gdd_base10": summary.total_gdd_base10,
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
                    "min_temp_c": d.min_temp_c,
                    "wind_speed_max_kmh": d.wind_speed_max_kmh,
                    "rain_probability_pct": d.rain_probability_pct,
                    "humidity_mean_pct": d.humidity_mean_pct,
                    "gdd_base10": d.gdd_base10,
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
            "ndvi_std": getattr(sat_res, "ndvi_std", None),
            "uniformity_score_pct": getattr(sat_res, "uniformity_score_pct", None),
            "quadrant_stats": getattr(sat_res, "quadrant_stats", None),
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


def generate_whatsapp_brief(
    outcome: AnalysisOutcome,
    lang: str = "en",
    generated_at: datetime | None = None,
) -> str:
    """Create a concise, mobile-ready WhatsApp/SMS brief in the selected language."""
    now_utc = generated_at or datetime.now(timezone.utc)
    req = outcome.request
    area = req.area
    lat, lon = area.center
    weather_res = outcome.weather.result if isinstance(outcome.weather.result, WeatherResult) else None
    sat_res = outcome.satellite.result if isinstance(outcome.satellite.result, SatelliteResult) else None

    if lang == "hi":
        lines = [
            f"🌾 *CropScope खेत सारांश* ({now_utc.strftime('%d %b %Y')})",
            f"🌱 *फसल:* {req.crop} ({req.growth_stage})",
            f"📍 *क्षेत्रफल:* {area.area_ha:.2f} हेक्टेयर ({area.area_acres:.2f} एकड़) · {lat:.4f}°, {lon:.4f}°",
        ]
        if weather_res:
            summary = compute_agro_climatic_summary(weather_res)
            windows = evaluate_operational_windows(weather_res)
            plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
            spray_dates = ", ".join(d.strftime("%d %b") for d in windows.spraying_favorable_days[:3]) or "कोई अनुकूल दिन नहीं"
            lines.extend([
                f"🌦️ *7-दिन मौसम:* वर्षा {summary.total_rain_mm:.1f} मिमी | फसल मांग ETc {plan.total_etc_mm:.1f} मिमी (अंतर {plan.crop_net_balance_mm:+.1f} मिमी)",
                f"🚿 *स्प्रे खिड़की:* {len(windows.spraying_favorable_days)}/7 दिन ({spray_dates})",
            ])
        if sat_res and sat_res.mean_ndvi is not None:
            hotspot = summarize_scouting_hotspot(getattr(sat_res, "quadrant_stats", None), getattr(sat_res, "uniformity_score_pct", None))
            lines.append(f"🛰️ *सैटेलाइट ({sat_res.acquired_at_utc.strftime('%d %b')}):* औसत NDVI {sat_res.mean_ndvi:.3f}")
            if hotspot:
                lines.append(f"🧭 *खेत निरीक्षण:* {hotspot}")
        if outcome.suggestions:
            lines.append(f"✅ *प्रमुख सुझाव:* {outcome.suggestions[0].candidate.title}")
        lines.append("⚠️ _सिंचाई या छिड़काव से पहले खेत की मिट्टी व फसल की प्रत्यक्ष जांच अवश्य करें।_")
        return "\n".join(lines)

    if lang == "pa":
        lines = [
            f"🌾 *CropScope ਖੇਤ ਰਿਪੋਰਟ* ({now_utc.strftime('%d %b %Y')})",
            f"🌱 *ਫ਼ਸਲ:* {req.crop} ({req.growth_stage})",
            f"📍 *ਰਕਬਾ:* {area.area_ha:.2f} ha ({area.area_acres:.2f} ac) · {lat:.4f}°, {lon:.4f}°",
        ]
        if weather_res:
            summary = compute_agro_climatic_summary(weather_res)
            windows = evaluate_operational_windows(weather_res)
            plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
            lines.append(f"🌦️ *7-ਦਿਨ ਮੌਸਮ:* ਮੀਂਹ {summary.total_rain_mm:.1f} mm | ਮੰਗ ETc {plan.total_etc_mm:.1f} mm (ਫ਼ਰਕ {plan.crop_net_balance_mm:+.1f} mm)")
            lines.append(f"🚿 *ਸਪਰੇਅ ਦਿਨ:* {len(windows.spraying_favorable_days)}/7 ਦਿਨ")
        if sat_res and sat_res.mean_ndvi is not None:
            lines.append(f"🛰️ *ਸੈਟੇਲਾਈਟ ({sat_res.acquired_at_utc.strftime('%d %b')}):* ਔਸਤ NDVI {sat_res.mean_ndvi:.3f}")
        if outcome.suggestions:
            lines.append(f"✅ *ਮੁੱਖ ਸਲਾਹ:* {outcome.suggestions[0].candidate.title}")
        lines.append("⚠️ _ਸਪਰੇਅ ਜਾਂ ਸਿੰਚਾਈ ਤੋਂ ਪਹਿਲਾਂ ਖੇਤ ਦੀ ਖ਼ੁਦ ਜਾਂਚ ਜ਼ਰੂਰ ਕਰੋ।_")
        return "\n".join(lines)

    lines = [
        f"🌾 *CropScope Field Brief* ({now_utc.strftime('%d %b %Y')})",
        f"🌱 *Crop:* {req.crop} ({req.growth_stage})",
        f"📍 *Area:* {area.area_ha:.2f} ha ({area.area_acres:.2f} ac) · {lat:.4f}°, {lon:.4f}°",
    ]
    if weather_res:
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)
        plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
        spray_dates = ", ".join(d.strftime("%a %d %b") for d in windows.spraying_favorable_days[:3]) or "None forecast"
        lines.extend([
            f"🌦️ *7-Day Weather:* Rain {summary.total_rain_mm:.1f} mm | Crop ETc {plan.total_etc_mm:.1f} mm (Kc={plan.kc:.2f}, Net {plan.crop_net_balance_mm:+.1f} mm)",
            f"🚿 *Safe Spray Days:* {len(windows.spraying_favorable_days)}/7 ({spray_dates})",
        ])
        if summary.max_wind_kmh is not None and summary.max_wind_kmh >= 15.0:
            lines.append(f"💨 *Peak Wind:* {summary.max_wind_kmh:.1f} km/h (watch drift)")
        if summary.min_temp_c is not None and summary.min_temp_c <= 5.0:
            lines.append(f"❄️ *Min Temp:* {summary.min_temp_c:.1f} °C (cold/frost alert)")
    if sat_res and sat_res.mean_ndvi is not None:
        lines.append(f"🛰️ *Satellite ({sat_res.acquired_at_utc.strftime('%d %b')}):* Mean NDVI {sat_res.mean_ndvi:.3f} ({sat_res.valid_pixel_percent:.0f}% clear)")
        hotspot = summarize_scouting_hotspot(getattr(sat_res, "quadrant_stats", None), getattr(sat_res, "uniformity_score_pct", None))
        if hotspot:
            lines.append(f"🧭 *Scouting Cue:* {hotspot}")
    if outcome.suggestions:
        lines.append(f"✅ *Top Check:* {outcome.suggestions[0].candidate.title}")
    lines.append("⚠️ _Decision support only: confirm field soil moisture & crop conditions on site._")
    return "\n".join(lines)


def build_whatsapp_share_url(brief_text: str) -> str:
    """Build a zero-cost client-side WhatsApp pre-filled share URL."""
    return f"https://wa.me/?text={quote(brief_text)}"


def generate_advisory_html(outcome: AnalysisOutcome, generated_at: datetime | None = None) -> str:
    """Generate a self-contained, printable HTML5 visual advisory report."""
    now_utc = generated_at or datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    req = outcome.request
    area = req.area
    lat_c, lon_c = area.center
    esc = html.escape

    weather_res = outcome.weather.result if isinstance(outcome.weather.result, WeatherResult) else None
    sat_res = outcome.satellite.result if isinstance(outcome.satellite.result, SatelliteResult) else None

    weather_html = "<p class='muted'>Weather forecast unavailable for this run.</p>"
    if weather_res:
        summary = compute_agro_climatic_summary(weather_res)
        windows = evaluate_operational_windows(weather_res)
        plan = compute_crop_water_plan(weather_res, req.crop, req.growth_stage)
        alerts = generate_weather_alerts(weather_res)
        alerts_html = "".join(
            f"<li><strong>{esc(a.category)}:</strong> {esc(a.message)}</li>" for a in alerts
        )
        rows_html = []
        for d in summary.days:
            min_t = f"{d.min_temp_c:.1f}°C" if d.min_temp_c is not None else "—"
            wind = f"{d.wind_speed_max_kmh:.1f} km/h" if d.wind_speed_max_kmh is not None else "—"
            rows_html.append(
                f"<tr><td>{esc(d.day.isoformat())}</td><td>{d.rain_mm:.1f}</td><td>{d.max_temp_c:.1f}</td>"
                f"<td>{esc(min_t)}</td><td>{esc(wind)}</td><td>{d.et0_mm:.1f}</td>"
                f"<td>{d.net_balance_mm:+.1f}</td><td>{esc(d.suitability)}</td></tr>"
            )
        weather_html = (
            f"<div class='kpi-grid'>"
            f"<div class='kpi'><span>7-Day Rain</span><strong>{summary.total_rain_mm:.1f} mm</strong></div>"
            f"<div class='kpi'><span>Crop ETc (Kc={plan.kc:.2f})</span><strong>{plan.total_etc_mm:.1f} mm</strong></div>"
            f"<div class='kpi'><span>Crop Net (P − ETc)</span><strong>{plan.crop_net_balance_mm:+.1f} mm</strong></div>"
            f"<div class='kpi'><span>Est. Deficit Vol.</span><strong>{plan.deficit_liters_per_acre:,.0f} L/ac</strong></div>"
            f"<div class='kpi'><span>Spray / Machinery Days</span><strong>{len(windows.spraying_favorable_days)} / {len(windows.machinery_accessible_days)} of 7</strong></div>"
            f"</div>"
            f"<ul class='alerts'>{alerts_html}</ul>"
            f"<table><thead><tr><th>Date</th><th>Rain (mm)</th><th>Max (°C)</th><th>Min</th><th>Wind</th>"
            f"<th>ET₀ (mm)</th><th>Net (mm)</th><th>Suitability</th></tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table>"
        )

    sat_html = "<p class='muted'>Satellite observation unavailable for this run.</p>"
    if sat_res:
        tci_bytes = getattr(sat_res, "true_color_png", None)
        ndvi_bytes = sat_res.ndvi_png
        imgs = []
        if tci_bytes:
            tci_b64 = base64.b64encode(tci_bytes).decode("ascii")
            imgs.append(
                f"<div class='img-card'><div class='img-title'>Sentinel-2 True Color (TCI)</div>"
                f"<img src='data:image/png;base64,{tci_b64}' alt='True Color Satellite View' /></div>"
            )
        if ndvi_bytes:
            ndvi_b64 = base64.b64encode(ndvi_bytes).decode("ascii")
            imgs.append(
                f"<div class='img-card'><div class='img-title'>Cloud-Masked NDVI Vigor</div>"
                f"<img src='data:image/png;base64,{ndvi_b64}' alt='NDVI Map' /></div>"
            )
        quads = getattr(sat_res, "quadrant_stats", None)
        uniformity = getattr(sat_res, "uniformity_score_pct", None)
        hotspot = summarize_scouting_hotspot(quads, uniformity)
        quad_html = ""
        if quads:
            quad_items = "".join(
                f"<li><strong>{esc(qn)}:</strong> Mean NDVI {qv['mean_ndvi']:.3f} ({qv['low_vigor_pct']:.1f}% sparse/bare)</li>"
                for qn, qv in quads.items()
            )
            quad_html = f"<p><strong>Spatial Scouting:</strong> {esc(hotspot)}</p><ul>{quad_items}</ul>"
        ndvi_val = f"{sat_res.mean_ndvi:.3f}" if sat_res.mean_ndvi is not None else "N/A"
        savi_val = f"{sat_res.mean_savi:.3f}" if getattr(sat_res, "mean_savi", None) is not None else "N/A"
        unif_val = f"{uniformity:.1f}%" if uniformity is not None else "N/A"
        sat_html = (
            f"<div class='kpi-grid'>"
            f"<div class='kpi'><span>Scene ID</span><strong>{esc(sat_res.scene_id)}</strong></div>"
            f"<div class='kpi'><span>Acquired</span><strong>{esc(sat_res.acquired_at_utc.strftime('%Y-%m-%d'))}</strong></div>"
            f"<div class='kpi'><span>Mean NDVI</span><strong>{esc(ndvi_val)}</strong></div>"
            f"<div class='kpi'><span>Mean SAVI</span><strong>{esc(savi_val)}</strong></div>"
            f"<div class='kpi'><span>Uniformity</span><strong>{esc(unif_val)}</strong></div>"
            f"</div>"
            f"<div class='img-row'>{''.join(imgs)}</div>"
            f"{quad_html}"
        )

    sugg_html = "<p class='muted'>No supported management checks for this run.</p>"
    if outcome.suggestions:
        cards = []
        for idx, item in enumerate(outcome.suggestions, 1):
            ev = " ".join(e.text for e in item.evidence)
            cards.append(
                f"<div class='check'><h4>{idx}. {esc(item.candidate.title)}</h4>"
                f"<p>{esc(item.candidate.action)}</p>"
                f"<div class='muted'>Evidence: {esc(ev)}</div></div>"
            )
        sugg_html = "".join(cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CropScope Field Advisory — {esc(req.crop)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #0f172a; margin: 24px auto; max-width: 920px; padding: 0 16px; line-height: 1.5; }}
    .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 18px; gap: 12px; }}
    .title {{ font-size: 22px; font-weight: 700; margin: 0; }}
    .muted {{ color: #475569; font-size: 13px; }}
    .print-btn {{ background: #d9480f; color: #fff; border: none; padding: 8px 14px; font-weight: 600; cursor: pointer; }}
    h2 {{ font-size: 16px; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 22px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 12px 0; }}
    .kpi {{ border: 1px solid #cbd5e1; padding: 10px 12px; background: #f8fafc; }}
    .kpi span {{ display: block; font-size: 11px; text-transform: uppercase; color: #475569; }}
    .kpi strong {{ font-size: 15px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
    th {{ background: #f1f5f9; }}
    .img-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin: 12px 0; }}
    .img-card {{ border: 1px solid #cbd5e1; padding: 8px; background: #fff; }}
    .img-title {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; text-transform: uppercase; }}
    .img-card img {{ width: 100%; height: auto; display: block; image-rendering: pixelated; }}
    .check {{ border-left: 3px solid #d9480f; padding: 6px 12px; margin-bottom: 10px; background: #fff7ed; }}
    .check h4 {{ margin: 0 0 4px 0; }}
    .disclaimer {{ margin-top: 24px; padding: 12px; background: #f1f5f9; border: 1px solid #cbd5e1; font-size: 12px; }}
    @media print {{ .print-btn {{ display: none; }} body {{ margin: 0; }} }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 class="title">CropScope — Field Advisory Report</h1>
      <div class="muted">Generated: {esc(timestamp_str)} · Crop: <strong>{esc(req.crop)}</strong> ({esc(req.growth_stage)})</div>
      <div class="muted">Area: {esc(area.formatted_area())} · Center: {lat_c:.5f}°, {lon_c:.5f}°</div>
    </div>
    <button class="print-btn" onclick="window.print()">Print / Save PDF</button>
  </div>
  <p class="muted"><strong>Stage Guidance:</strong> {esc(get_growth_stage_guidance(req.growth_stage))}</p>
  <h2>1. 7-Day Agro-Climatic &amp; Crop Water Forecast</h2>
  {weather_html}
  <h2>2. Sentinel-2 Satellite Canopy Observation</h2>
  {sat_html}
  <h2>3. Prioritized Field Checks</h2>
  {sugg_html}
  <div class="disclaimer">
    <strong>Scientific Boundaries:</strong> CropScope is a decision-support prototype. Forecast weather and FAO-56 Kc estimates are not soil moisture sensor readings, and NDVI indicates spectral greenness rather than specific crop disease or yield. Always inspect conditions on site before irrigating or applying agrochemicals.
  </div>
</body>
</html>"""


