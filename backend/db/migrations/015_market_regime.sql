-- R5: daily market regime classification (Bull / Bear / High-Vol / Sideways) per market.
CREATE TABLE IF NOT EXISTS market_regime (
    id           SERIAL PRIMARY KEY,
    date         DATE NOT NULL,
    market       TEXT NOT NULL,             -- 'US' | 'INDIA'
    regime       TEXT NOT NULL,             -- 'bull' | 'bear' | 'high_vol' | 'sideways'
    index_symbol TEXT,
    index_close  NUMERIC(18, 6),
    sma_50       NUMERIC(18, 6),
    sma_200      NUMERIC(18, 6),
    vix          NUMERIC(18, 6),
    realized_vol NUMERIC(18, 6),
    breadth_pct  NUMERIC(18, 6),
    reason       TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date, market)
);

CREATE INDEX IF NOT EXISTS idx_market_regime_market_date ON market_regime (market, date DESC);
