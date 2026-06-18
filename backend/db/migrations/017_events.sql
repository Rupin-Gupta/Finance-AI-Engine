-- R8: macro event calendar (FOMC / CPI / RBI MPC / Budget …) for the event-proximity gate.
CREATE TABLE IF NOT EXISTS market_events (
    id          SERIAL PRIMARY KEY,
    event_date  DATE NOT NULL,
    event_type  TEXT NOT NULL,        -- FOMC | CPI | RBI_MPC | BUDGET | GDP | ...
    region      TEXT NOT NULL,        -- US | INDIA | GLOBAL
    impact      TEXT NOT NULL,        -- high | medium | low
    title       TEXT NOT NULL,
    source      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (event_date, event_type, region)
);

CREATE INDEX IF NOT EXISTS idx_market_events_date ON market_events (event_date);
