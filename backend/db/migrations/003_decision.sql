-- Decision Intelligence tables

CREATE TABLE IF NOT EXISTS sentiment (
    id           SERIAL PRIMARY KEY,
    symbol       TEXT NOT NULL,
    date         DATE NOT NULL,
    score        NUMERIC(6,4) NOT NULL,
    headline_count INT NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'yahoo_rss',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, date)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id             SERIAL PRIMARY KEY,
    symbol         TEXT NOT NULL,
    forecast_date  DATE NOT NULL,
    predicted_close NUMERIC(12,4) NOT NULL,
    lower_bound    NUMERIC(12,4) NOT NULL,
    upper_bound    NUMERIC(12,4) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, forecast_date)
);

CREATE TABLE IF NOT EXISTS decisions (
    id             SERIAL PRIMARY KEY,
    symbol         TEXT NOT NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('BUY','SELL','HOLD')),
    confidence     NUMERIC(5,4) NOT NULL,
    signals_json   JSONB NOT NULL DEFAULT '{}',
    risk_level     TEXT NOT NULL CHECK (risk_level IN ('Low','Medium','High','Extreme')),
    explanation    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentiment_symbol_date ON sentiment (symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_forecasts_symbol_date ON forecasts (symbol, forecast_date ASC);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol_created ON decisions (symbol, created_at DESC);
