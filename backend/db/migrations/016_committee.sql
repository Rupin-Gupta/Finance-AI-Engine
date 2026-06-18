-- R10: multi-agent investment committee verdict stored alongside the decision.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS committee_json JSONB;
