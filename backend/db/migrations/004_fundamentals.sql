-- Fundamental data and earnings calendar tables

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol              TEXT PRIMARY KEY REFERENCES stocks(symbol) ON DELETE CASCADE,
    market_cap          BIGINT,
    pe_trailing         NUMERIC(10,2),
    pe_forward          NUMERIC(10,2),
    peg_ratio           NUMERIC(8,4),
    eps_trailing        NUMERIC(10,4),
    eps_forward         NUMERIC(10,4),
    revenue             BIGINT,
    gross_margins       NUMERIC(6,4),
    profit_margins      NUMERIC(6,4),
    price_to_book       NUMERIC(8,4),
    beta                NUMERIC(6,4),
    dividend_yield      NUMERIC(6,4),
    week_52_high        NUMERIC(12,4),
    week_52_low         NUMERIC(12,4),
    analyst_target      NUMERIC(12,4),
    analyst_rating      TEXT,
    analyst_count       INT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS earnings_calendar (
    id              SERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    earnings_date   DATE NOT NULL,
    eps_estimate    NUMERIC(10,4),
    eps_actual      NUMERIC(10,4),
    surprise_pct    NUMERIC(8,4),
    UNIQUE (symbol, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_symbol_date ON earnings_calendar (symbol, earnings_date DESC);
