-- Signal performance snapshots: per-signal accuracy + return attribution over time.
-- Written weekly by signal_snapshot_run → enables trend/drift analysis (R3 history).
CREATE TABLE IF NOT EXISTS signal_performance (
    snapshot_date     DATE NOT NULL,
    signal            TEXT NOT NULL,
    horizon_days      INT  NOT NULL,
    lookback_days     INT  NOT NULL,
    active_count      INT  NOT NULL,
    accuracy          NUMERIC(6,4),
    attributed_return NUMERIC(12,6),
    avg_weight        NUMERIC(8,4),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, signal, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_signal_perf_signal ON signal_performance (signal, snapshot_date DESC);
