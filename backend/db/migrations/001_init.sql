CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS stocks (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    sector      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_data (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      TEXT NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    timestamp   TIMESTAMPTZ NOT NULL,
    open        NUMERIC NOT NULL,
    high        NUMERIC NOT NULL,
    low         NUMERIC NOT NULL,
    close       NUMERIC NOT NULL,
    volume      BIGINT NOT NULL,
    UNIQUE (symbol, timestamp)
);

CREATE TABLE IF NOT EXISTS financial_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url  TEXT UNIQUE NOT NULL,
    doc_type    TEXT NOT NULL,
    chunk_count INT NOT NULL DEFAULT 0,
    ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID NOT NULL REFERENCES financial_reports(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    text            TEXT NOT NULL,
    embedding_vector BYTEA,
    index_version   INT NOT NULL DEFAULT 0,
    UNIQUE (doc_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    value       NUMERIC NOT NULL,
    threshold   NUMERIC NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key     TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    query       TEXT NOT NULL,
    response    TEXT NOT NULL,
    sources     JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_market_data_symbol_ts ON market_data (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts (symbol, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc ON embeddings (doc_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, started_at DESC);
