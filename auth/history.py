"""Scan outcome persistence and history timeline widgets for CropScope.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from analysis import AnalysisOutcome
from db.scans import list_scans_for_farmer, list_scans_for_field, save_scan
from models import SatelliteResult, WeatherResult


def record_scan_outcome(
    outcome: AnalysisOutcome,
    farmer_id: str,
    field_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Transform AnalysisOutcome and save into persistent scan records."""
    try:
        req = outcome.request
        bbox = (req.area.south, req.area.west, req.area.north, req.area.east)

        weather_res = outcome.weather.result if isinstance(outcome.weather.result, WeatherResult) else None
        sat_res = outcome.satellite.result if isinstance(outcome.satellite.result, SatelliteResult) else None

        weather_ok = weather_res is not None
        rain_7d = sum(d.rain_mm for d in weather_res.days) if weather_res else 0.0
        et0_7d = sum(d.et0_mm for d in weather_res.days) if weather_res else 0.0
        net_water = rain_7d - et0_7d
        water_status = "Surplus" if net_water > 0 else ("Deficit" if net_water < 0 else "Balanced")
        safe_spray = all(d.rain_mm < 2.0 for d in weather_res.days[:2]) if weather_res else True

        wt_payload = None
        if weather_res:
            wt_payload = {
                "timezone": weather_res.timezone,
                "fetched_at_utc": weather_res.fetched_at_utc.isoformat(),
                "source_url": weather_res.source_url,
                "daily_forecast": [
                    {"day": d.day.isoformat(), "rain_mm": d.rain_mm, "max_temp_c": d.max_temp_c, "et0_mm": d.et0_mm}
                    for d in weather_res.days
                ],
            }

        sat_ok = sat_res is not None
        mean_ndvi = sat_res.mean_ndvi if sat_res else None
        med_ndvi = sat_res.median_ndvi if sat_res else None
        mean_savi = sat_res.mean_savi if sat_res else None
        valid_px = sat_res.valid_pixel_percent if sat_res else None
        cloud_pct = sat_res.scene_cloud_percent if sat_res else None

        st_payload = None
        if sat_res:
            st_payload = {
                "scene_id": sat_res.scene_id,
                "acquired_at_utc": sat_res.acquired_at_utc.isoformat(),
                "platform": sat_res.platform,
                "mgrs_tile": sat_res.mgrs_tile,
                "sun_elevation": sat_res.sun_elevation,
                "sun_azimuth": sat_res.sun_azimuth,
                "canopy_zones": sat_res.canopy_zones,
                "quality_message": sat_res.quality_message,
                "catalog_url": sat_res.catalog_url,
                "thumbnail_url": sat_res.scene_thumbnail_url,
            }

        recs_payload = []
        for s in outcome.suggestions:
            recs_payload.append(
                {
                    "action_id": s.candidate.id,
                    "title": s.candidate.title,
                    "description": s.candidate.action,
                    "category": "Agronomy",
                    "urgency": "High" if s.candidate.priority <= 20 else "Medium",
                    "evidence_source": outcome.suggestion_source,
                }
            )

        saved = save_scan(
            farmer_id=farmer_id,
            field_id=field_id,
            crop_name=req.crop,
            growth_stage=req.growth_stage,
            bbox=bbox,
            weather_ok=weather_ok,
            rain_7d_mm=rain_7d,
            et0_7d_mm=et0_7d,
            net_water_mm=net_water,
            water_status=water_status,
            safe_to_spray_48h=safe_spray,
            satellite_ok=sat_ok,
            mean_ndvi=mean_ndvi,
            median_ndvi=med_ndvi,
            mean_savi=mean_savi,
            valid_pixels_pct=valid_px,
            cloud_cover_pct=cloud_pct,
            advisory_source=outcome.suggestion_source,
            weather_telemetry=wt_payload,
            satellite_telemetry=st_payload,
            recommendations=recs_payload,
            db_path=db_path,
        )
        return saved
    except Exception as exc:
        st.caption(f"Note: Scan history autosave encountered: {exc}")
        return None


def render_scan_history_timeline(
    farmer_id: str,
    field_id: Optional[str] = None,
    current_lang: str = "en",
) -> None:
    """Render historical scans timeline for the farmer."""
    all_farmer_scans = list_scans_for_farmer(farmer_id, limit=20)
    if not all_farmer_scans:
        st.info("No past scans recorded yet. Run an analysis above to save your first scan.")
        return

    # If field_id is set, see if there are scans for this field
    field_scans = [s for s in all_farmer_scans if s.get("field_id") == field_id] if field_id else []

    scans_to_display = all_farmer_scans
    if field_id and field_scans:
        col_f1, col_f2 = st.columns([2, 1], vertical_alignment="center")
        with col_f1:
            st.markdown(
                f"""
                <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone-3);
                            text-transform: uppercase; letter-spacing: 0.08em; margin: 12px 0 8px;">
                    📜 Past Scan Records // पिछले स्कैन ({len(field_scans)} active · {len(all_farmer_scans)} total)
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_f2:
            show_all = st.checkbox("Show all parcels", value=False, key="chk_show_all_scans")
            if not show_all:
                scans_to_display = field_scans
    else:
        st.markdown(
            f"""
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone-3);
                        text-transform: uppercase; letter-spacing: 0.08em; margin: 12px 0 8px;">
                📜 Past Scan Records // पिछले स्कैन ({len(all_farmer_scans)} total)
            </div>
            """,
            unsafe_allow_html=True,
        )
        if field_id and not field_scans:
            st.caption("ℹ️ Showing all farm scans (no scans recorded specifically for this active parcel yet).")

    for scan in scans_to_display:
        scan_date = scan.get("scanned_at", "")[:16].replace("T", " ")
        crop = scan.get("crop_name", "Crop")
        stage = scan.get("growth_stage", "Stage")
        ndvi_str = f"NDVI: {scan['mean_ndvi']:.3f}" if scan.get("mean_ndvi") is not None else "No Sat"
        water_str = f"Net: {scan.get('net_water_mm', 0):+.1f} mm ({scan.get('water_status', '-')})"
        spray_str = "Spray: Safe" if scan.get("safe_to_spray_48h") else "Spray: Unsafe"

        st.markdown(
            f"""
            <div style="background: var(--ink-1); border: 1px solid var(--line);
                        padding: 10px 14px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <strong style="color: var(--bone); font-family: var(--font-mono);">{crop}</strong>
                        <span style="color: var(--bone-3); font-size: 12px;"> · {stage}</span>
                    </div>
                    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone-3);">
                        📅 {scan_date} UTC
                    </div>
                </div>
                <div style="font-family: var(--font-mono); font-size: 11.5px; color: var(--bone-2); margin-top: 6px; display: flex; gap: 14px; flex-wrap: wrap;">
                    <span>🌱 <strong>{ndvi_str}</strong></span>
                    <span>💧 <strong>{water_str}</strong></span>
                    <span>🛡️ <strong>{spray_str}</strong></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
