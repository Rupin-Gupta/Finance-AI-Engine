-- P3: per-symbol stop-loss config (override the vol-derived recommended stop).
-- NOTE: `trailing` is a reserved SQL keyword → column named is_trailing.
CREATE TABLE IF NOT EXISTS position_stops (
    symbol      TEXT PRIMARY KEY,
    stop_pct    NUMERIC(6,4),              -- NULL → use the recommended (vol+risk) stop
    is_trailing BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
