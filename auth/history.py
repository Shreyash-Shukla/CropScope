"""Scan outcome persistence and history timeline widgets for CropScope.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from analysis import AnalysisOutcome
from db.fields import list_fields
from db.scans import list_scans_for_farmer, list_scans_for_field, save_scan
from models import AnalysisArea, SatelliteResult, WeatherResult


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
        safe_spray = (
            all(
                d.rain_mm < 2.0
                and d.max_temp_c < 32.0
                and (d.wind_speed_max_kmh is None or d.wind_speed_max_kmh < 15.0)
                for d in weather_res.days[:2]
            )
            if weather_res
            else True
        )

        wt_payload = None
        if weather_res:
            wt_payload = {
                "timezone": weather_res.timezone,
                "fetched_at_utc": weather_res.fetched_at_utc.isoformat(),
                "source_url": weather_res.source_url,
                "daily_forecast": [
                    {
                        "day": d.day.isoformat(),
                        "rain_mm": d.rain_mm,
                        "max_temp_c": d.max_temp_c,
                        "et0_mm": d.et0_mm,
                        "min_temp_c": d.min_temp_c,
                        "wind_speed_max_kmh": d.wind_speed_max_kmh,
                        "rain_probability_pct": d.rain_probability_pct,
                        "humidity_mean_pct": d.humidity_mean_pct,
                    }
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


def _csv_safe_text(val: Any) -> str:
    """Neutralize spreadsheet formula prefixes in exported CSV text cells."""
    text = "" if val is None else str(val)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _bbox_matches(scan: Dict[str, Any], bbox: Tuple[float, float, float, float], tol: float = 1e-4) -> bool:
    """Return True if scan bounding box matches target (south, west, north, east)."""
    try:
        return (
            abs(float(scan["bbox_south"]) - bbox[0]) <= tol
            and abs(float(scan["bbox_west"]) - bbox[1]) <= tol
            and abs(float(scan["bbox_north"]) - bbox[2]) <= tol
            and abs(float(scan["bbox_east"]) - bbox[3]) <= tol
        )
    except (KeyError, TypeError, ValueError):
        return False


def compute_scan_trend_metrics(
    scans: List[Dict[str, Any]],
    *,
    field_id: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> Dict[str, Any]:
    """Compute chronological NDVI/SAVI/water deltas and chart series from scan rows."""
    filtered = list(scans)
    if field_id:
        by_field = [s for s in filtered if s.get("field_id") == field_id]
        if by_field:
            filtered = by_field
        elif bbox is not None:
            filtered = [s for s in filtered if _bbox_matches(s, bbox)]
    elif bbox is not None:
        by_bbox = [s for s in filtered if _bbox_matches(s, bbox)]
        if by_bbox:
            filtered = by_bbox

    ordered = sorted(filtered, key=lambda s: str(s.get("scanned_at") or ""))
    ndvi_rows = [s for s in ordered if s.get("mean_ndvi") is not None]
    savi_rows = [s for s in ordered if s.get("mean_savi") is not None]

    latest_ndvi = float(ndvi_rows[-1]["mean_ndvi"]) if ndvi_rows else None
    prev_ndvi = float(ndvi_rows[-2]["mean_ndvi"]) if len(ndvi_rows) >= 2 else None
    ndvi_delta = round(latest_ndvi - prev_ndvi, 4) if (latest_ndvi is not None and prev_ndvi is not None) else None
    if ndvi_delta is None:
        ndvi_direction = "Baseline"
    elif ndvi_delta >= 0.02:
        ndvi_direction = "Improving"
    elif ndvi_delta <= -0.02:
        ndvi_direction = "Declining"
    else:
        ndvi_direction = "Stable"

    latest_savi = float(savi_rows[-1]["mean_savi"]) if savi_rows else None
    prev_savi = float(savi_rows[-2]["mean_savi"]) if len(savi_rows) >= 2 else None
    savi_delta = round(latest_savi - prev_savi, 4) if (latest_savi is not None and prev_savi is not None) else None

    latest_net_water = float(ordered[-1]["net_water_mm"]) if ordered and ordered[-1].get("net_water_mm") is not None else None
    prev_net_water = float(ordered[-2]["net_water_mm"]) if len(ordered) >= 2 and ordered[-2].get("net_water_mm") is not None else None
    net_water_delta = round(latest_net_water - prev_net_water, 2) if (latest_net_water is not None and prev_net_water is not None) else None

    series: List[Dict[str, Any]] = []
    for idx, s in enumerate(ordered, 1):
        ts_raw = str(s.get("scanned_at") or "")
        label = f"{ts_raw[:10]} #{idx}" if ts_raw else f"Scan #{idx}"
        series.append({
            "Scan": label,
            "Date": ts_raw[:16].replace("T", " "),
            "Crop": s.get("crop_name", "Crop"),
            "Mean NDVI": float(s["mean_ndvi"]) if s.get("mean_ndvi") is not None else None,
            "Mean SAVI": float(s["mean_savi"]) if s.get("mean_savi") is not None else None,
            "Net Water (mm)": float(s["net_water_mm"]) if s.get("net_water_mm") is not None else None,
            "Rain 7d (mm)": float(s["rain_7d_mm"]) if s.get("rain_7d_mm") is not None else None,
            "ET0 7d (mm)": float(s["et0_7d_mm"]) if s.get("et0_7d_mm") is not None else None,
        })

    return {
        "scan_count": len(ordered),
        "ndvi_scan_count": len(ndvi_rows),
        "latest_ndvi": latest_ndvi,
        "prev_ndvi": prev_ndvi,
        "ndvi_delta": ndvi_delta,
        "ndvi_direction": ndvi_direction,
        "latest_savi": latest_savi,
        "savi_delta": savi_delta,
        "latest_net_water": latest_net_water,
        "net_water_delta": net_water_delta,
        "prev_scanned_at": str(ndvi_rows[-2].get("scanned_at", ""))[:10] if len(ndvi_rows) >= 2 else None,
        "series": series,
    }


def build_parcel_comparison_rows(
    fields: List[Dict[str, Any]],
    scans: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build latest health & water comparison rows across a farmer's saved parcels."""
    ordered_desc = sorted(scans, key=lambda s: str(s.get("scanned_at") or ""), reverse=True)
    rows: List[Dict[str, Any]] = []
    for f in fields:
        fid = f.get("id")
        bbox = (
            float(f.get("bbox_south", 0.0)),
            float(f.get("bbox_west", 0.0)),
            float(f.get("bbox_north", 0.0)),
            float(f.get("bbox_east", 0.0)),
        )
        match = next(
            (s for s in ordered_desc if s.get("field_id") == fid or _bbox_matches(s, bbox)),
            None,
        )
        rows.append({
            "Parcel": f.get("name", "Field"),
            "Area (ha)": round(float(f.get("area_ha", 0.0)), 2),
            "Area (ac)": round(float(f.get("area_acres", 0.0)), 2),
            "Irrigation": f.get("irrigation_source") or "—",
            "Latest Crop": match.get("crop_name") if match else "Not scanned",
            "Stage": match.get("growth_stage") if match else "—",
            "Mean NDVI": round(float(match["mean_ndvi"]), 3) if (match and match.get("mean_ndvi") is not None) else None,
            "Net Water (mm)": round(float(match["net_water_mm"]), 1) if (match and match.get("net_water_mm") is not None) else None,
            "48h Spray": ("Safe" if match.get("safe_to_spray_48h") else "Hold") if match else "—",
            "Last Scanned": str(match.get("scanned_at", ""))[:16].replace("T", " ") if match else "—",
        })
    return rows


def export_scans_csv(
    scans: List[Dict[str, Any]],
    fields_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Serialize scan history records into RFC 4180 CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "scanned_at_utc",
        "field_name",
        "crop_name",
        "growth_stage",
        "bbox_south",
        "bbox_west",
        "bbox_north",
        "bbox_east",
        "rain_7d_mm",
        "et0_7d_mm",
        "net_water_mm",
        "water_status",
        "safe_to_spray_48h",
        "mean_ndvi",
        "median_ndvi",
        "mean_savi",
        "valid_pixels_pct",
        "cloud_cover_pct",
        "advisory_source",
    ])
    fields_map = fields_by_id or {}
    for s in scans:
        f_rec = fields_map.get(str(s.get("field_id") or ""))
        f_name = f_rec.get("name") if f_rec else "Ad-hoc Selection"
        writer.writerow([
            _csv_safe_text(s.get("scanned_at", "")),
            _csv_safe_text(f_name),
            _csv_safe_text(s.get("crop_name", "")),
            _csv_safe_text(s.get("growth_stage", "")),
            s.get("bbox_south", ""),
            s.get("bbox_west", ""),
            s.get("bbox_north", ""),
            s.get("bbox_east", ""),
            s.get("rain_7d_mm", ""),
            s.get("et0_7d_mm", ""),
            s.get("net_water_mm", ""),
            _csv_safe_text(s.get("water_status", "")),
            "Yes" if s.get("safe_to_spray_48h") else "No",
            s.get("mean_ndvi") if s.get("mean_ndvi") is not None else "",
            s.get("median_ndvi") if s.get("median_ndvi") is not None else "",
            s.get("mean_savi") if s.get("mean_savi") is not None else "",
            s.get("valid_pixels_pct") if s.get("valid_pixels_pct") is not None else "",
            s.get("cloud_cover_pct") if s.get("cloud_cover_pct") is not None else "",
            _csv_safe_text(s.get("advisory_source", "")),
        ])
    return buf.getvalue()


def _render_trend_and_csv_widgets(
    scans: List[Dict[str, Any]],
    fields: List[Dict[str, Any]],
    *,
    field_id: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    key_prefix: str = "hist",
) -> None:
    """Render shared trend metrics, progression charts, parcel table, and CSV download."""
    trend = compute_scan_trend_metrics(scans, field_id=field_id, bbox=bbox)
    k1, k2, k3 = st.columns(3)
    k1.metric("Recorded Scans", str(trend["scan_count"]))
    if trend["latest_ndvi"] is not None:
        delta_txt = (
            f"{trend['ndvi_delta']:+.3f} vs {trend['prev_scanned_at']}"
            if trend["ndvi_delta"] is not None
            else trend["ndvi_direction"]
        )
        k2.metric("Latest NDVI", f"{trend['latest_ndvi']:.3f}", delta=delta_txt)
    else:
        k2.metric("Latest NDVI", "—")
    if trend["latest_net_water"] is not None:
        w_delta = f"{trend['net_water_delta']:+.1f} mm" if trend["net_water_delta"] is not None else None
        k3.metric("Latest Net Water", f"{trend['latest_net_water']:+.1f} mm", delta=w_delta)
    else:
        k3.metric("Latest Net Water", "—")

    series = trend["series"]
    if len(series) >= 2:
        df_trend = pd.DataFrame(series)
        c_left, c_right = st.columns(2)
        with c_left:
            if df_trend["Mean NDVI"].notna().sum() >= 2:
                ndvi_cols = ["Mean NDVI"]
                if df_trend["Mean SAVI"].notna().sum() >= 2:
                    ndvi_cols.append("Mean SAVI")
                st.markdown("**Vegetation Index Trend (NDVI / SAVI)**")
                st.line_chart(df_trend, x="Scan", y=ndvi_cols, height=220)
        with c_right:
            if df_trend["Net Water (mm)"].notna().sum() >= 2:
                st.markdown("**7-Day Net Water Balance Trend (mm)**")
                st.bar_chart(df_trend, x="Scan", y=["Rain 7d (mm)", "ET0 7d (mm)"], height=220)

    if len(fields) >= 2:
        st.markdown("**Saved Parcel Health Comparison**")
        comp_rows = build_parcel_comparison_rows(fields, scans)
        st.dataframe(pd.DataFrame(comp_rows), hide_index=True, width="stretch")

    fields_by_id = {f["id"]: f for f in fields if "id" in f}
    csv_text = export_scans_csv(scans, fields_by_id=fields_by_id)
    st.download_button(
        "📥 Export Scan History (CSV)",
        data=csv_text,
        file_name="cropscope_scan_history.csv",
        mime="text/csv",
        key=f"{key_prefix}_export_csv",
        use_container_width=True,
    )


def render_farm_analytics_panel(
    farmer_id: str,
    area: Optional[AnalysisArea] = None,
    field_id: Optional[str] = None,
    current_lang: str = "en",
) -> None:
    """Render on-page scan trends, multi-parcel comparison, and CSV history export."""
    scans = list_scans_for_farmer(farmer_id, limit=50)
    if not scans:
        return
    fields = list_fields(farmer_id)
    bbox = (area.south, area.west, area.north, area.east) if area is not None else None
    with st.expander(f"📈 Farm Scan Trends, Parcel Comparison & CSV Export ({len(scans)} scans)", expanded=False):
        _render_trend_and_csv_widgets(
            scans,
            fields,
            field_id=field_id,
            bbox=bbox,
            key_prefix="main_analytics",
        )


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
    fields = list_fields(farmer_id)

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

    _render_trend_and_csv_widgets(
        scans_to_display,
        fields,
        field_id=field_id,
        key_prefix="drawer_history",
    )

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
