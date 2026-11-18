"""Farm field / parcel boundary persistence and management.
"""

from __future__ import annotations

import datetime
import math
import uuid
from typing import Any, Dict, List, Optional, Tuple

from db.connection import (
    deserialize_json_field,
    get_sqlite_conn,
    get_supabase_client,
    is_supabase_configured,
    serialize_json_field,
)


def _approx_bbox_area_ha(south: float, west: float, north: float, east: float) -> float:
    """Calculate approximate area in hectares for lat/lon bounding box."""
    # 1 deg lat ~ 111.139 km
    # 1 deg lon ~ 111.139 * cos(mid_lat) km
    mid_lat = math.radians((south + north) / 2.0)
    lat_dist_km = abs(north - south) * 111.139
    lon_dist_km = abs(east - west) * 111.139 * math.cos(mid_lat)
    area_sqkm = lat_dist_km * lon_dist_km
    return round(area_sqkm * 100.0, 2)  # 1 sq km = 100 ha


def _clean_field_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure JSON types and booleans are properly parsed."""
    res = dict(row_dict)
    res["boundary_geojson"] = deserialize_json_field(res.get("boundary_geojson"))
    res["is_primary"] = bool(res.get("is_primary", False))
    res["is_archived"] = bool(res.get("is_archived", False))
    return res


def save_field(
    farmer_id: str,
    name: str,
    bbox: Tuple[float, float, float, float],
    boundary_geojson: Optional[Dict[str, Any]] = None,
    boundary_type: str = "rectangle",
    area_ha: Optional[float] = None,
    soil_type: Optional[str] = None,
    irrigation_source: Optional[str] = None,
    is_primary: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a farm field boundary for a farmer.

    Args:
        farmer_id: Farmer UUID.
        name: User-defined name for field (e.g. 'खेत 1 - नहर वाला').
        bbox: (south, west, north, east) coordinates.
        boundary_geojson: GeoJSON geometry or Feature dict.
        boundary_type: 'rectangle' or 'polygon'.
        area_ha: Area in hectares (auto-computed if omitted).
        soil_type: Optional soil type description.
        irrigation_source: e.g. 'Canal', 'Tube Well', 'Rainfed'.
        is_primary: Mark as default primary field.
        db_path: Custom SQLite path (for tests).
    """
    south, west, north, east = bbox
    computed_ha = area_ha if (area_ha is not None and area_ha > 0) else _approx_bbox_area_ha(south, west, north, east)
    computed_acres = round(computed_ha * 2.47105, 2)

    if boundary_geojson is None:
        boundary_geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        }

    field_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            if is_primary:
                sb.table("fields").update({"is_primary": False}).eq("farmer_id", farmer_id).execute()

            payload = {
                "id": field_id,
                "farmer_id": farmer_id,
                "name": name.strip(),
                "boundary_type": boundary_type,
                "boundary_geojson": boundary_geojson,
                "bbox_south": south,
                "bbox_west": west,
                "bbox_north": north,
                "bbox_east": east,
                "area_ha": computed_ha,
                "area_acres": computed_acres,
                "soil_type": soil_type,
                "irrigation_source": irrigation_source,
                "is_primary": is_primary,
                "is_archived": False,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            res = sb.table("fields").insert(payload).execute()
            if res.data:
                return _clean_field_row(res.data[0])

    # SQLite
    conn = get_sqlite_conn(db_path)
    with conn:
        if is_primary:
            conn.execute("UPDATE fields SET is_primary = 0 WHERE farmer_id = ?", (farmer_id,))

        conn.execute(
            """
            INSERT INTO fields (
                id, farmer_id, name, boundary_type, boundary_geojson,
                bbox_south, bbox_west, bbox_north, bbox_east,
                area_ha, area_acres, soil_type, irrigation_source,
                is_primary, is_archived, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                field_id,
                farmer_id,
                name.strip(),
                boundary_type,
                serialize_json_field(boundary_geojson),
                south,
                west,
                north,
                east,
                computed_ha,
                computed_acres,
                soil_type,
                irrigation_source,
                1 if is_primary else 0,
                now_iso,
                now_iso,
            ),
        )

    res_field = get_field_by_id(field_id, db_path=db_path)
    assert res_field is not None
    return res_field


def get_field_by_id(field_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve field by its UUID."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = sb.table("fields").select("*").eq("id", field_id).execute()
            if res.data:
                return _clean_field_row(res.data[0])
            return None

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM fields WHERE id = ?", (field_id,))
    row = cur.fetchone()
    if not row:
        return None
    return _clean_field_row(dict(row))


def list_fields(
    farmer_id: str,
    include_archived: bool = False,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all saved fields for a farmer."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            query = sb.table("fields").select("*").eq("farmer_id", farmer_id)
            if not include_archived:
                query = query.eq("is_archived", False)
            res = query.order("is_primary", desc=True).order("created_at", desc=True).execute()
            return [_clean_field_row(r) for r in res.data]

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    if include_archived:
        cur.execute(
            """
            SELECT * FROM fields
            WHERE farmer_id = ?
            ORDER BY is_primary DESC, created_at DESC
            """,
            (farmer_id,),
        )
    else:
        cur.execute(
            """
            SELECT * FROM fields
            WHERE farmer_id = ? AND is_archived = 0
            ORDER BY is_primary DESC, created_at DESC
            """,
            (farmer_id,),
        )
    return [_clean_field_row(dict(r)) for r in cur.fetchall()]


def archive_field(field_id: str, db_path: Optional[str] = None) -> bool:
    """Soft delete / archive a field."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            sb.table("fields").update({"is_archived": True, "updated_at": now_iso}).eq("id", field_id).execute()
            return True

    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute("UPDATE fields SET is_archived = 1, updated_at = ? WHERE id = ?", (now_iso, field_id))
    return True


def set_primary_field(farmer_id: str, field_id: str, db_path: Optional[str] = None) -> bool:
    """Set specified field as the farmer's primary field."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            sb.table("fields").update({"is_primary": False}).eq("farmer_id", farmer_id).execute()
            sb.table("fields").update({"is_primary": True, "updated_at": now_iso}).eq("id", field_id).execute()
            return True

    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute("UPDATE fields SET is_primary = 0 WHERE farmer_id = ?", (farmer_id,))
        conn.execute("UPDATE fields SET is_primary = 1, updated_at = ? WHERE id = ?", (now_iso, field_id))
    return True
