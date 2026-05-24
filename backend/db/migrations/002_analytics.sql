CREATE TABLE IF NOT EXISTS analytics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      TEXT NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    timestamp   TIMESTAMPTZ NOT NULL,
    sma_20      NUMERIC,
    ema_20      NUMERIC,
    rsi_14      NUMERIC,
    volatility_20 NUMERIC,
    momentum_10 NUMERIC,
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_analytics_symbol_ts ON analytics (symbol, timestamp DESC);
