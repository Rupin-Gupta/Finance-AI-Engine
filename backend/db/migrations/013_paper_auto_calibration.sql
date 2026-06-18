-- R1.2 + R2.1 + R2.3: paper-trade equity history + a cheap calibration read cache.

-- Equity-curve history for the paper portfolio (snapshotted each auto-run / on demand).
-- Lets us report Sharpe / drawdown / total-return OVER TIME (reuses analytics/performance math).
CREATE TABLE IF NOT EXISTS paper_equity_history (
    portfolio       TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    equity          NUMERIC(18,2) NOT NULL,
    cash            NUMERIC(18,2) NOT NULL,
    positions_value NUMERIC(18,2) NOT NULL,
    total_return    NUMERIC(12,6),
    PRIMARY KEY (portfolio, ts)
);
CREATE INDEX IF NOT EXISTS idx_paper_equity_ts ON paper_equity_history (portfolio, ts);

-- Precomputed calibration read-cache: the snapshot job scores history offline and writes
-- the reliability curve + per-recommendation hit rate here, so the (hot) decision endpoint
-- can map a new call's confidence → calibrated win probability with ONE cheap row read
-- instead of re-scoring all history per request.
CREATE TABLE IF NOT EXISTS calibration_summary (
    horizon_days           INT PRIMARY KEY,
    reliability_json       JSONB NOT NULL,
    by_recommendation_json JSONB NOT NULL,
    overall_hit_rate       NUMERIC(6,4),
    evaluated_count        INT NOT NULL DEFAULT 0,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
