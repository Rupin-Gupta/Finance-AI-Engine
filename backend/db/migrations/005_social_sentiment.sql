-- Expand sentiment UNIQUE to include source so multiple sources can coexist per (symbol, date).
-- Old: UNIQUE(symbol, date)  →  New: UNIQUE(symbol, date, source)
ALTER TABLE sentiment DROP CONSTRAINT IF EXISTS sentiment_symbol_date_key;
ALTER TABLE sentiment ADD CONSTRAINT sentiment_symbol_date_source_key UNIQUE (symbol, date, source);
