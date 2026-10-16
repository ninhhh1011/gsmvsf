CREATE TABLE IF NOT EXISTS state_snapshots (
    snapshot_id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('traffic', 'station', 'queue')),
    entity_id text NOT NULL,
    timestamp timestamptz NOT NULL,
    source text NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version = 1),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, entity_id, timestamp)
);

-- Fresh-window enumeration complements the per-entity timestamp head index.
CREATE INDEX IF NOT EXISTS state_snapshots_fresh_window_idx
    ON state_snapshots (kind, timestamp DESC, entity_id);

CREATE TABLE IF NOT EXISTS candidate_searches (
    candidate_search_id text PRIMARY KEY,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
