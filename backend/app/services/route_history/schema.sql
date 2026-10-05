-- Route History Scale - PostgreSQL Schema
-- ========================================

-- Historical routes table
CREATE TABLE IF NOT EXISTS historical_routes (
    route_id VARCHAR(100) PRIMARY KEY,
    trip_id VARCHAR(100) NOT NULL,
    driver_id VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    origin_lat DOUBLE PRECISION NOT NULL,
    origin_lng DOUBLE PRECISION NOT NULL,
    dest_lat DOUBLE PRECISION NOT NULL,
    dest_lng DOUBLE PRECISION NOT NULL,
    total_distance_m DOUBLE PRECISION NOT NULL,
    segment_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for origin proximity search
CREATE INDEX IF NOT EXISTS idx_historical_routes_origin
    ON historical_routes (origin_lat, origin_lng);

-- Index for destination proximity search
CREATE INDEX IF NOT EXISTS idx_historical_routes_dest
    ON historical_routes (dest_lat, dest_lng);

-- Index for driver queries
CREATE INDEX IF NOT EXISTS idx_historical_routes_driver
    ON historical_routes (driver_id);

-- Index for time window queries
CREATE INDEX IF NOT EXISTS idx_historical_routes_started_at
    ON historical_routes (started_at);


-- Historical route segments table
CREATE TABLE IF NOT EXISTS historical_route_segments (
    id BIGSERIAL PRIMARY KEY,
    route_id VARCHAR(100) NOT NULL REFERENCES historical_routes(route_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    segment_id VARCHAR(100) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    length_m DOUBLE PRECISION NOT NULL,
    UNIQUE (route_id, seq)
);

-- Index for segment lookups
CREATE INDEX IF NOT EXISTS idx_historical_route_segments_route
    ON historical_route_segments (route_id);

-- Index for segment queries (which routes contain this segment)
CREATE INDEX IF NOT EXISTS idx_historical_route_segments_segment
    ON historical_route_segments (segment_id);


-- Historical route H3 cells table (Resolution 11)
CREATE TABLE IF NOT EXISTS historical_route_h3 (
    id BIGSERIAL PRIMARY KEY,
    route_id VARCHAR(100) NOT NULL REFERENCES historical_routes(route_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    h3_cell_res11 VARCHAR(20) NOT NULL,
    UNIQUE (route_id, seq)
);

-- Index for H3 cell queries (inverted index)
CREATE INDEX IF NOT EXISTS idx_historical_route_h3_cell
    ON historical_route_h3 (h3_cell_res11);

-- Index for route lookups
CREATE INDEX IF NOT EXISTS idx_historical_route_h3_route
    ON historical_route_h3 (route_id);


-- Route families table
CREATE TABLE IF NOT EXISTS route_families (
    family_id VARCHAR(100) PRIMARY KEY,
    representative_route_id VARCHAR(100) NOT NULL,
    origin_lat DOUBLE PRECISION NOT NULL,
    origin_lng DOUBLE PRECISION NOT NULL,
    dest_lat DOUBLE PRECISION NOT NULL,
    dest_lng DOUBLE PRECISION NOT NULL,
    direction_bearing DOUBLE PRECISION NOT NULL,
    trip_count INTEGER NOT NULL DEFAULT 0,
    unique_driver_count INTEGER NOT NULL DEFAULT 0,
    weighted_support DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for family context queries
CREATE INDEX IF NOT EXISTS idx_route_families_origin
    ON route_families (origin_lat, origin_lng);

CREATE INDEX IF NOT EXISTS idx_route_families_dest
    ON route_families (dest_lat, dest_lng);


-- Route family members table
CREATE TABLE IF NOT EXISTS route_family_members (
    id BIGSERIAL PRIMARY KEY,
    family_id VARCHAR(100) NOT NULL REFERENCES route_families(family_id) ON DELETE CASCADE,
    route_id VARCHAR(100) NOT NULL REFERENCES historical_routes(route_id) ON DELETE CASCADE,
    time_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    recency_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    UNIQUE (family_id, route_id)
);

-- Index for member lookups
CREATE INDEX IF NOT EXISTS idx_route_family_members_family
    ON route_family_members (family_id);

CREATE INDEX IF NOT EXISTS idx_route_family_members_route
    ON route_family_members (route_id);


-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_historical_routes_updated_at ON historical_routes;
CREATE TRIGGER update_historical_routes_updated_at
    BEFORE UPDATE ON historical_routes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_route_families_updated_at ON route_families;
CREATE TRIGGER update_route_families_updated_at
    BEFORE UPDATE ON route_families
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
