-- Corporate actions: splits / bonus / dividends / rights.
-- Splits & bonus silently break raw price history (a 2:1 split looks like a -50% crash)
-- → corrupts signals + backtests. We capture them here for visibility, dividend
-- total-return, and back-adjusting any raw price series (see analytics/corporate_actions.py).
CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol      TEXT NOT NULL,
    action_date DATE NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('split','bonus','dividend','rights')),
    ratio       NUMERIC(18,6),   -- split/bonus ratio: shares_after / shares_before (2.0 = 2:1)
    amount      NUMERIC(18,6),   -- dividend cash per share
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, action_date, action_type)
);

CREATE INDEX IF NOT EXISTS idx_corp_actions_symbol ON corporate_actions (symbol, action_date DESC);
