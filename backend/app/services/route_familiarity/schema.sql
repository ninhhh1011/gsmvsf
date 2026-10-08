CREATE SCHEMA IF NOT EXISTS realtime;

CREATE TABLE IF NOT EXISTS realtime.route_familiarity_routes (
    driver_id text NOT NULL,
    trip_id text NOT NULL,
    completed_at timestamptz NOT NULL,
    distance_m double precision NOT NULL CHECK (distance_m > 0 AND distance_m <= 100000),
    resolution smallint NOT NULL CHECK (resolution = 11),
    cells text[] NOT NULL CHECK (cardinality(cells) BETWEEN 1 AND 2000),
    cell_distances_m double precision[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (driver_id, trip_id),
    CHECK (cardinality(cells) = cardinality(cell_distances_m)),
    CHECK (array_position(cells, NULL) IS NULL),
    CHECK (array_position(cell_distances_m, NULL) IS NULL),
    CHECK (0 <= ALL(cell_distances_m)),
    CHECK (array_position(cell_distances_m, 'NaN'::float8) IS NULL),
    CHECK (array_position(cell_distances_m, 'Infinity'::float8) IS NULL),
    CHECK (array_position(cell_distances_m, '-Infinity'::float8) IS NULL)
);

CREATE INDEX IF NOT EXISTS route_familiarity_driver_time_idx
    ON realtime.route_familiarity_routes USING btree (driver_id, completed_at DESC);
CREATE INDEX IF NOT EXISTS route_familiarity_cells_idx
    ON realtime.route_familiarity_routes USING gin (cells);
