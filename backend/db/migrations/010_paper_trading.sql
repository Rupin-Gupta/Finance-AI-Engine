-- Paper trading: virtual portfolio executed against real prices.
-- Single-user app → a named singleton portfolio ('default').
CREATE TABLE IF NOT EXISTS paper_portfolio (
    name          TEXT PRIMARY KEY,
    starting_cash NUMERIC(18,2) NOT NULL,
    cash          NUMERIC(18,2) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_positions (
    portfolio  TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    quantity   NUMERIC(18,6) NOT NULL,
    avg_cost   NUMERIC(18,6) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (portfolio, symbol)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id           BIGSERIAL PRIMARY KEY,
    portfolio    TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    quantity     NUMERIC(18,6) NOT NULL,
    price        NUMERIC(18,6) NOT NULL,
    fee          NUMERIC(18,6) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18,6),
    ts           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_ts ON paper_trades (portfolio, ts DESC);
