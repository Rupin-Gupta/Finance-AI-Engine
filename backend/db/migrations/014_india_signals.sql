-- P5: India-specific market signals.
-- Market-wide institutional flow + options positioning + pre-market direction. These are
-- one row per trading day (not per-symbol) and act as a shared overlay for .NS/.BO names.
CREATE TABLE IF NOT EXISTS india_market_signals (
    date            DATE PRIMARY KEY,
    fii_net_cr      NUMERIC(14,2),   -- FII net cash-equity flow, ₹ crore (+inflow / -outflow)
    dii_net_cr      NUMERIC(14,2),   -- DII net cash-equity flow, ₹ crore
    pcr             NUMERIC(8,4),    -- NIFTY put/call open-interest ratio
    gift_nifty_pct  NUMERIC(8,4),    -- Gift Nifty pre-market move vs prev close (fraction)
    gift_nifty_level NUMERIC(12,2),
    source          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bulk / block deals are per-symbol (informational; not yet an engine signal).
CREATE TABLE IF NOT EXISTS bulk_block_deals (
    id         BIGSERIAL PRIMARY KEY,
    deal_date  DATE NOT NULL,
    symbol     TEXT NOT NULL,
    client     TEXT,
    side       TEXT CHECK (side IN ('BUY','SELL')),
    quantity   BIGINT,
    price      NUMERIC(14,4),
    deal_type  TEXT,               -- 'bulk' | 'block'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (deal_date, symbol, client, side, quantity, deal_type)
);
CREATE INDEX IF NOT EXISTS idx_bulk_deals_symbol ON bulk_block_deals (symbol, deal_date DESC);
