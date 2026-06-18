-- Auto-tuned signal weights (R4). Each row is one optimization run; the engine uses
-- the latest `promoted` set (else the hardcoded SIGNAL_WEIGHTS default).
CREATE TABLE IF NOT EXISTS signal_weights (
    id                        BIGSERIAL PRIMARY KEY,
    weights_json              JSONB NOT NULL,
    in_sample_return          NUMERIC(12,6),
    out_of_sample_return      NUMERIC(12,6),
    base_out_of_sample_return NUMERIC(12,6),
    improvement               NUMERIC(12,6),
    promoted                  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_weights_promoted
    ON signal_weights (promoted, created_at DESC);
