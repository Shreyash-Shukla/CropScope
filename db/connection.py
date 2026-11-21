"""CropScope Database Connection & Engine Dispatcher.

Supports a hybrid architecture:
- Supabase (PostgreSQL) when SUPABASE_URL and SUPABASE_ANON_KEY are provided.
- Local SQLite (zero-config, cropscope.db) as automatic offline / development fallback.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from supabase import Client, create_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    Client = Any  # type: ignore
    create_client = None  # type: ignore
    _SUPABASE_AVAILABLE = False

_DEFAULT_DB_FILE = "cropscope.db"
_local = threading.local()

# SQLite Schema DDL mirroring migrations/0001_initial_schema.sql
SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS farmers (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    phone_number TEXT UNIQUE,
    full_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT,
    mpin_hash TEXT,
    preferred_language TEXT NOT NULL DEFAULT 'en',
    state TEXT,
    district TEXT,
    village TEXT,
    role TEXT NOT NULL DEFAULT 'farmer',
    is_onboarded INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_farmers_email ON farmers(email);
CREATE INDEX IF NOT EXISTS idx_farmers_phone ON farmers(phone_number);

CREATE TABLE IF NOT EXISTS fields (
    id TEXT PRIMARY KEY,
    farmer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    boundary_type TEXT NOT NULL DEFAULT 'rectangle',
    boundary_geojson TEXT NOT NULL,
    bbox_south REAL NOT NULL,
    bbox_west REAL NOT NULL,
    bbox_north REAL NOT NULL,
    bbox_east REAL NOT NULL,
    area_ha REAL NOT NULL DEFAULT 0.0,
    area_acres REAL NOT NULL DEFAULT 0.0,
    soil_type TEXT,
    irrigation_source TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(farmer_id) REFERENCES farmers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fields_farmer ON fields(farmer_id);

CREATE TABLE IF NOT EXISTS crop_cycles (
    id TEXT PRIMARY KEY,
    field_id TEXT NOT NULL,
    crop_name TEXT NOT NULL,
    variety TEXT,
    season TEXT,
    current_stage TEXT NOT NULL,
    sowing_date TEXT,
    expected_harvest_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crop_cycles_field ON crop_cycles(field_id);

CREATE TABLE IF NOT EXISTS analysis_scans (
    id TEXT PRIMARY KEY,
    field_id TEXT,
    farmer_id TEXT NOT NULL,
    crop_name TEXT NOT NULL,
    growth_stage TEXT NOT NULL,
    bbox_south REAL NOT NULL,
    bbox_west REAL NOT NULL,
    bbox_north REAL NOT NULL,
    bbox_east REAL NOT NULL,
    weather_ok INTEGER NOT NULL DEFAULT 0,
    rain_7d_mm REAL NOT NULL DEFAULT 0.0,
    et0_7d_mm REAL NOT NULL DEFAULT 0.0,
    net_water_mm REAL NOT NULL DEFAULT 0.0,
    water_status TEXT,
    safe_to_spray_48h INTEGER DEFAULT 1,
    satellite_ok INTEGER NOT NULL DEFAULT 0,
    mean_ndvi REAL,
    median_ndvi REAL,
    mean_savi REAL,
    valid_pixels_pct REAL,
    cloud_cover_pct REAL,
    advisory_source TEXT,
    tci_image_path TEXT,
    ndvi_image_path TEXT,
    scanned_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE SET NULL,
    FOREIGN KEY(farmer_id) REFERENCES farmers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scans_field ON analysis_scans(field_id, scanned_at);
CREATE INDEX IF NOT EXISTS idx_scans_farmer ON analysis_scans(farmer_id, scanned_at);

CREATE TABLE IF NOT EXISTS weather_telemetry (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL UNIQUE,
    timezone TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    source_url TEXT,
    daily_forecast TEXT NOT NULL,
    spraying_days INTEGER NOT NULL DEFAULT 0,
    machinery_days INTEGER NOT NULL DEFAULT 0,
    scouting_days INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(scan_id) REFERENCES analysis_scans(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS satellite_telemetry (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL UNIQUE,
    scene_id TEXT NOT NULL,
    acquired_at_utc TEXT NOT NULL,
    platform TEXT,
    mgrs_tile TEXT,
    sun_elevation REAL,
    sun_azimuth REAL,
    canopy_zones TEXT,
    quality_message TEXT,
    catalog_url TEXT,
    thumbnail_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(scan_id) REFERENCES analysis_scans(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS advisory_recommendations (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 1,
    action_id TEXT NOT NULL,
    category TEXT NOT NULL,
    urgency TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_source TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(scan_id) REFERENCES analysis_scans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_advisory_scan ON advisory_recommendations(scan_id, rank);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    farmer_id TEXT NOT NULL,
    field_id TEXT,
    scan_id TEXT,
    title TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(farmer_id) REFERENCES farmers(id) ON DELETE CASCADE,
    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE SET NULL,
    FOREIGN KEY(scan_id) REFERENCES analysis_scans(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_farmer ON chat_sessions(farmer_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    dossier_snapshot TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
"""


def get_db_path() -> str:
    """Return path to SQLite database file."""
    return os.getenv("CROPSCOPE_DB_PATH", _DEFAULT_DB_FILE)


def is_supabase_configured() -> bool:
    """Check if Supabase credentials are provided and client library is installed."""
    if not _SUPABASE_AVAILABLE:
        return False
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    return bool(url and key)


def get_supabase_client() -> Optional[Client]:
    """Return Supabase client if configured, else None."""
    if not is_supabase_configured():
        return None
    url = os.environ["SUPABASE_URL"].strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")]
    key = os.environ["SUPABASE_ANON_KEY"].strip()
    try:
        return create_client(url, key)
    except Exception:
        return None


def get_sqlite_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return thread-local SQLite connection with schema initialized."""
    target_path = db_path or get_db_path()
    
    # In-memory connections or custom paths per call
    if target_path == ":memory:" or db_path:
        conn = sqlite3.connect(target_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SQLITE_SCHEMA)
        return conn

    # Thread-local cache for standard db file
    conn = getattr(_local, "conn", None)
    current_path = getattr(_local, "db_path", None)
    if conn is None or current_path != target_path:
        conn = sqlite3.connect(target_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(SQLITE_SCHEMA)
        _local.conn = conn
        _local.db_path = target_path
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Ensure database schema is created and initialized."""
    get_sqlite_conn(db_path)


def serialize_json_field(val: Any) -> Optional[str]:
    """Serialize Python object to JSON string for SQLite storage."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def deserialize_json_field(val: Any) -> Any:
    """Deserialize JSON string from database row if necessary."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (ValueError, TypeError):
        return val
