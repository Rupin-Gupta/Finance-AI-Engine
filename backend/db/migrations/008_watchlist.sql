-- Watchlist / holdings: persisted symbols with optional position (qty + cost basis).
-- Single-user app keyed by API key, so symbol is the natural primary key.
CREATE TABLE IF NOT EXISTS watchlist (
    symbol      TEXT PRIMARY KEY,
    quantity    NUMERIC(18,6),
    cost_basis  NUMERIC(18,6),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
