"""Scan outcome and agronomic telemetry persistence.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional, Union

from db.connection import (
    deserialize_json_field,
    get_sqlite_conn,
    get_supabase_client,
    is_supabase_configured,
    serialize_json_field,
)


def _clean_scan_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Format boolean and numeric fields in scan row."""
    res = dict(row_dict)
    res["weather_ok"] = bool(res.get("weather_ok", False))
    res["safe_to_spray_48h"] = bool(res.get("safe_to_spray_48h", True))
    res["satellite_ok"] = bool(res.get("satellite_ok", False))
    return res


def save_scan(
    farmer_id: str,
    crop_name: str,
    growth_stage: str,
    bbox: tuple[float, float, float, float],
    field_id: Optional[str] = None,
    weather_ok: bool = False,
    rain_7d_mm: float = 0.0,
    et0_7d_mm: float = 0.0,
    net_water_mm: float = 0.0,
    water_status: Optional[str] = None,
    safe_to_spray_48h: bool = True,
    satellite_ok: bool = False,
    mean_ndvi: Optional[float] = None,
    median_ndvi: Optional[float] = None,
    mean_savi: Optional[float] = None,
    valid_pixels_pct: Optional[float] = None,
    cloud_cover_pct: Optional[float] = None,
    advisory_source: Optional[str] = None,
    tci_image_path: Optional[str] = None,
    ndvi_image_path: Optional[str] = None,
    weather_telemetry: Optional[Dict[str, Any]] = None,
    satellite_telemetry: Optional[Dict[str, Any]] = None,
    recommendations: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist an analysis scan along with telemetry and recommendations."""
    scan_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    south, west, north, east = bbox

    scan_payload = {
        "id": scan_id,
        "field_id": field_id,
        "farmer_id": farmer_id,
        "crop_name": crop_name,
        "growth_stage": growth_stage,
        "bbox_south": south,
        "bbox_west": west,
        "bbox_north": north,
        "bbox_east": east,
        "weather_ok": weather_ok,
        "rain_7d_mm": round(rain_7d_mm, 2),
        "et0_7d_mm": round(et0_7d_mm, 2),
        "net_water_mm": round(net_water_mm, 2),
        "water_status": water_status,
        "safe_to_spray_48h": safe_to_spray_48h,
        "satellite_ok": satellite_ok,
        "mean_ndvi": round(mean_ndvi, 4) if mean_ndvi is not None else None,
        "median_ndvi": round(median_ndvi, 4) if median_ndvi is not None else None,
        "mean_savi": round(mean_savi, 4) if mean_savi is not None else None,
        "valid_pixels_pct": round(valid_pixels_pct, 2) if valid_pixels_pct is not None else None,
        "cloud_cover_pct": round(cloud_cover_pct, 2) if cloud_cover_pct is not None else None,
        "advisory_source": advisory_source,
        "tci_image_path": tci_image_path,
        "ndvi_image_path": ndvi_image_path,
        "scanned_at": now_iso,
    }

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            sb.table("analysis_scans").insert(scan_payload).execute()
            if weather_telemetry:
                wt = dict(weather_telemetry)
                wt["id"] = str(uuid.uuid4())
                wt["scan_id"] = scan_id
                wt["created_at"] = now_iso
                sb.table("weather_telemetry").insert(wt).execute()
            if satellite_telemetry:
                st = dict(satellite_telemetry)
                st["id"] = str(uuid.uuid4())
                st["scan_id"] = scan_id
                st["created_at"] = now_iso
                sb.table("satellite_telemetry").insert(st).execute()
            if recommendations:
                for idx, rec in enumerate(recommendations, 1):
                    r_item = {
                        "id": str(uuid.uuid4()),
                        "scan_id": scan_id,
                        "rank": idx,
                        "action_id": rec.get("action_id", f"action_{idx}"),
                        "category": rec.get("category", "General"),
                        "urgency": rec.get("urgency", "Medium"),
                        "title": rec.get("title", ""),
                        "description": rec.get("description", ""),
                        "evidence_source": rec.get("evidence_source", advisory_source),
                        "created_at": now_iso,
                    }
                    sb.table("advisory_recommendations").insert(r_item).execute()
            return get_scan_by_id(scan_id, db_path=db_path)  # type: ignore

    # SQLite
    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO analysis_scans (
                id, field_id, farmer_id, crop_name, growth_stage,
                bbox_south, bbox_west, bbox_north, bbox_east,
                weather_ok, rain_7d_mm, et0_7d_mm, net_water_mm, water_status,
                safe_to_spray_48h, satellite_ok, mean_ndvi, median_ndvi,
                mean_savi, valid_pixels_pct, cloud_cover_pct, advisory_source,
                tci_image_path, ndvi_image_path, scanned_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                scan_id,
                field_id,
                farmer_id,
                crop_name,
                growth_stage,
                south,
                west,
                north,
                east,
                1 if weather_ok else 0,
                round(rain_7d_mm, 2),
                round(et0_7d_mm, 2),
                round(net_water_mm, 2),
                water_status,
                1 if safe_to_spray_48h else 0,
                1 if satellite_ok else 0,
                round(mean_ndvi, 4) if mean_ndvi is not None else None,
                round(median_ndvi, 4) if median_ndvi is not None else None,
                round(mean_savi, 4) if mean_savi is not None else None,
                round(valid_pixels_pct, 2) if valid_pixels_pct is not None else None,
                round(cloud_cover_pct, 2) if cloud_cover_pct is not None else None,
                advisory_source,
                tci_image_path,
                ndvi_image_path,
                now_iso,
            ),
        )

        if weather_telemetry:
            conn.execute(
                """
                INSERT INTO weather_telemetry (
                    id, scan_id, timezone, fetched_at_utc, source_url,
                    daily_forecast, spraying_days, machinery_days, scouting_days, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    scan_id,
                    weather_telemetry.get("timezone", "UTC"),
                    weather_telemetry.get("fetched_at_utc", now_iso),
                    weather_telemetry.get("source_url"),
                    serialize_json_field(weather_telemetry.get("daily_forecast", [])),
                    weather_telemetry.get("spraying_days", 0),
                    weather_telemetry.get("machinery_days", 0),
                    weather_telemetry.get("scouting_days", 0),
                    now_iso,
                ),
            )

        if satellite_telemetry:
            conn.execute(
                """
                INSERT INTO satellite_telemetry (
                    id, scan_id, scene_id, acquired_at_utc, platform, mgrs_tile,
                    sun_elevation, sun_azimuth, canopy_zones, quality_message,
                    catalog_url, thumbnail_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    scan_id,
                    satellite_telemetry.get("scene_id", "unknown"),
                    satellite_telemetry.get("acquired_at_utc", now_iso),
                    satellite_telemetry.get("platform"),
                    satellite_telemetry.get("mgrs_tile"),
                    satellite_telemetry.get("sun_elevation"),
                    satellite_telemetry.get("sun_azimuth"),
                    serialize_json_field(satellite_telemetry.get("canopy_zones")),
                    satellite_telemetry.get("quality_message"),
                    satellite_telemetry.get("catalog_url"),
                    satellite_telemetry.get("thumbnail_url"),
                    now_iso,
                ),
            )

        if recommendations:
            for idx, rec in enumerate(recommendations, 1):
                conn.execute(
                    """
                    INSERT INTO advisory_recommendations (
                        id, scan_id, rank, action_id, category, urgency,
                        title, description, evidence_source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        scan_id,
                        idx,
                        rec.get("action_id", f"action_{idx}"),
                        rec.get("category", "General"),
                        rec.get("urgency", "Medium"),
                        rec.get("title", ""),
                        rec.get("description", ""),
                        rec.get("evidence_source", advisory_source),
                        now_iso,
                    ),
                )

    res_scan = get_scan_by_id(scan_id, db_path=db_path)
    assert res_scan is not None
    return res_scan


def get_scan_by_id(scan_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve scan with its associated recommendations."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = sb.table("analysis_scans").select("*").eq("id", scan_id).execute()
            if not res.data:
                return None
            scan = _clean_scan_row(res.data[0])
            recs = sb.table("advisory_recommendations").select("*").eq("scan_id", scan_id).order("rank").execute()
            scan["recommendations"] = recs.data or []
            return scan

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM analysis_scans WHERE id = ?", (scan_id,))
    row = cur.fetchone()
    if not row:
        return None
    scan = _clean_scan_row(dict(row))

    cur.execute("SELECT * FROM advisory_recommendations WHERE scan_id = ? ORDER BY rank ASC", (scan_id,))
    scan["recommendations"] = [dict(r) for r in cur.fetchall()]
    return scan


def list_scans_for_field(
    field_id: str,
    limit: int = 20,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent scans for a specific field."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = (
                sb.table("analysis_scans")
                .select("*")
                .eq("field_id", field_id)
                .order("scanned_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [_clean_scan_row(r) for r in res.data]

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM analysis_scans WHERE field_id = ? ORDER BY scanned_at DESC LIMIT ?",
        (field_id, limit),
    )
    return [_clean_scan_row(dict(r)) for r in cur.fetchall()]


def list_scans_for_farmer(
    farmer_id: str,
    limit: int = 20,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent scans across all fields for a farmer."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = (
                sb.table("analysis_scans")
                .select("*")
                .eq("farmer_id", farmer_id)
                .order("scanned_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [_clean_scan_row(r) for r in res.data]

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM analysis_scans WHERE farmer_id = ? ORDER BY scanned_at DESC LIMIT ?",
        (farmer_id, limit),
    )
    return [_clean_scan_row(dict(r)) for r in cur.fetchall()]
