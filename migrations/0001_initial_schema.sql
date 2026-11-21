-- CropScope: Initial Schema Migration (Phase 7)
-- Enables PostgreSQL UUID extension, tables for farmers, fields, crop cycles,
-- analysis scans, telemetry, advisories, and grounded chat sessions with Row-Level Security.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. FARMERS TABLE (Profile & Demographics)
CREATE TABLE IF NOT EXISTS farmers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE,
    phone_number VARCHAR(20) UNIQUE,
    full_name VARCHAR(120) NOT NULL DEFAULT '',
    password_hash VARCHAR(255),
    mpin_hash VARCHAR(255),
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
    state VARCHAR(100),
    district VARCHAR(100),
    village VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'farmer',
    is_onboarded BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_farmers_email ON farmers(email);
CREATE INDEX IF NOT EXISTS idx_farmers_phone ON farmers(phone_number);

-- 2. FIELDS / PARCELS
CREATE TABLE IF NOT EXISTS fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farmer_id UUID NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    boundary_type VARCHAR(20) NOT NULL DEFAULT 'rectangle',
    boundary_geojson JSONB NOT NULL,
    bbox_south DOUBLE PRECISION NOT NULL,
    bbox_west DOUBLE PRECISION NOT NULL,
    bbox_north DOUBLE PRECISION NOT NULL,
    bbox_east DOUBLE PRECISION NOT NULL,
    area_ha DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    area_acres DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    soil_type VARCHAR(60),
    irrigation_source VARCHAR(60),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fields_farmer ON fields(farmer_id) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_fields_bbox ON fields(bbox_south, bbox_west, bbox_north, bbox_east);

-- 3. CROP CYCLES
CREATE TABLE IF NOT EXISTS crop_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    field_id UUID NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    crop_name VARCHAR(80) NOT NULL,
    variety VARCHAR(100),
    season VARCHAR(30),
    current_stage VARCHAR(60) NOT NULL,
    sowing_date DATE,
    expected_harvest_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crop_cycles_field ON crop_cycles(field_id);

-- 4. ANALYSIS SCANS
CREATE TABLE IF NOT EXISTS analysis_scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    field_id UUID REFERENCES fields(id) ON DELETE SET NULL,
    farmer_id UUID NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
    crop_name VARCHAR(80) NOT NULL,
    growth_stage VARCHAR(60) NOT NULL,
    bbox_south DOUBLE PRECISION NOT NULL,
    bbox_west DOUBLE PRECISION NOT NULL,
    bbox_north DOUBLE PRECISION NOT NULL,
    bbox_east DOUBLE PRECISION NOT NULL,
    weather_ok BOOLEAN NOT NULL DEFAULT FALSE,
    rain_7d_mm DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    et0_7d_mm DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    net_water_mm DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    water_status VARCHAR(60),
    safe_to_spray_48h BOOLEAN DEFAULT TRUE,
    satellite_ok BOOLEAN NOT NULL DEFAULT FALSE,
    mean_ndvi DOUBLE PRECISION,
    median_ndvi DOUBLE PRECISION,
    mean_savi DOUBLE PRECISION,
    valid_pixels_pct DOUBLE PRECISION,
    cloud_cover_pct DOUBLE PRECISION,
    advisory_source VARCHAR(80),
    tci_image_path TEXT,
    ndvi_image_path TEXT,
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scans_field ON analysis_scans(field_id, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_scans_farmer ON analysis_scans(farmer_id, scanned_at DESC);

-- 5. WEATHER TELEMETRY
CREATE TABLE IF NOT EXISTS weather_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL REFERENCES analysis_scans(id) ON DELETE CASCADE,
    timezone VARCHAR(60) NOT NULL,
    fetched_at_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    source_url TEXT,
    daily_forecast JSONB NOT NULL,
    spraying_days INT NOT NULL DEFAULT 0,
    machinery_days INT NOT NULL DEFAULT 0,
    scouting_days INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_weather_scan ON weather_telemetry(scan_id);

-- 6. SATELLITE TELEMETRY
CREATE TABLE IF NOT EXISTS satellite_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL REFERENCES analysis_scans(id) ON DELETE CASCADE,
    scene_id VARCHAR(100) NOT NULL,
    acquired_at_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    platform VARCHAR(50),
    mgrs_tile VARCHAR(20),
    sun_elevation DOUBLE PRECISION,
    sun_azimuth DOUBLE PRECISION,
    canopy_zones JSONB,
    quality_message TEXT,
    catalog_url TEXT,
    thumbnail_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sat_scan ON satellite_telemetry(scan_id);

-- 7. ADVISORY RECOMMENDATIONS
CREATE TABLE IF NOT EXISTS advisory_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL REFERENCES analysis_scans(id) ON DELETE CASCADE,
    rank SMALLINT NOT NULL DEFAULT 1,
    action_id VARCHAR(60) NOT NULL,
    category VARCHAR(60) NOT NULL,
    urgency VARCHAR(30) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    evidence_source VARCHAR(60),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_advisory_scan ON advisory_recommendations(scan_id, rank);

-- 8. CHAT SESSIONS (Kisan Mitra Threads)
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farmer_id UUID NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
    field_id UUID REFERENCES fields(id) ON DELETE SET NULL,
    scan_id UUID REFERENCES analysis_scans(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_farmer ON chat_sessions(farmer_id, updated_at DESC);

-- 9. CHAT MESSAGES
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    dossier_snapshot JSONB,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at ASC);

-- ============================================================
-- 10. ROW LEVEL SECURITY (RLS) & PUBLIC API PERMISSIONS
-- Disable RLS on application tables so CropScope client can read/write directly
-- ============================================================
ALTER TABLE IF EXISTS farmers DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS fields DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS crop_cycles DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS analysis_scans DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS weather_telemetry DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS satellite_telemetry DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS advisory_recommendations DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS chat_sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS chat_messages DISABLE ROW LEVEL SECURITY;

-- Grant full read/write permissions to anon, authenticated, and service_role
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES TO anon, authenticated, service_role;
