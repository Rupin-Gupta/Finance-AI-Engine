# SPEC — AI-Powered Financial Intelligence & Market Analytics Platform

## §G Goal

Multi-source financial data → ETL → PostgreSQL + FAISS → analytics engine + RAG assistant + anomaly detection → FastAPI → Streamlit dashboard. Automate ingestion, reporting, & Q&A for financial analysts.

---

## §C Constraints

- C1. Async-first: all I/O non-blocking (FastAPI + asyncio + asyncpg).
- C2. Modular packages: `ingest`, `analytics`, `retrieval`, `rag`, `api`, `scheduler`, `ui` — ≤300 LOC each.
- C3. PostgreSQL ! primary store; FAISS index persisted to disk; no direct DB access from UI.
- C4. RAG response ! cite sources: `[{doc_id, chunk_id, score}]`.
- C5. Auth ! every `/v1/*` endpoint — API key header; 401 on failure.
- C6. Ingestion idempotent: same source URL re-run → no duplicate rows.
- C7. Secrets ∈ env vars / `.env`; ⊥ hardcoded.
- C8. Scheduler (APScheduler) ! run as background worker, not inline with API.
- C9. Anomaly detection runs post-ingest; results stored in `alerts` table.
- C10. LLM provider configurable via env (`OPENAI_API_KEY` | `GEMINI_API_KEY`); model via `LLM_MODEL` (current default `gemini-2.5-flash`).
- C11. Docker Compose ∀ services: api, worker, db, ui.
- C12. ETL ! validate schema, remove duplicates, handle nulls before DB write.

---

## §I External Surfaces

| id      | surface                                      | direction |
|---------|---------------------------------------------|-----------|
| I.yf    | Yahoo Finance (`yfinance`)                  | in        |
| I.fh    | Finnhub API (`FINNHUB_API_KEY`)             | in        |
| I.llm   | OpenAI / Gemini (`OPENAI_API_KEY` \| `GEMINI_API_KEY`) | out |
| I.emb   | Sentence Transformers (local model)         | out       |
| I.api   | FastAPI REST (`/v1/*`)                      | in/out    |
| I.db    | PostgreSQL (asyncpg)                        | out       |
| I.vec   | FAISS index (disk, `.faiss` + `.pkl`)       | out       |
| I.ui    | Streamlit + Plotly dashboard                | out       |
| I.sched | APScheduler (in-process or separate worker) | internal  |
| I.cfg   | `.env` / env vars                           | in        |

---

## §V Invariants

- V1. ∀ ingested doc → row in `financial_reports`: `{id, source_url, doc_type, ingested_at, chunk_count}`.
- V2. FAISS index version ! match `index_version` in `embeddings` table; rebuild on mismatch.
- V3. RAG response ! `{answer: str, sources: [{doc_id, chunk_id, score}]}`.
- V4. `market_data` rows ! `{symbol, timestamp, open, high, low, close, volume}`; no nulls in these 7 fields.
- V5. Analytics computed → stored in `market_data` extra cols or separate `analytics` table; ⊥ computed on-the-fly per request.
- V6. ∀ `/v1/*` req without valid API key → 401; ⊥ 200 on auth failure.
- V7. Ingestion idempotent: upsert on `(symbol, timestamp)` PK for `market_data`.
- V8. ∀ background job → row in `jobs`: `{id, type, status, started_at, finished_at, error}`.
- V9. Anomaly detection result → row in `alerts`: `{id, symbol, alert_type, value, threshold, detected_at}`.
- V10. Streamlit ! read via FastAPI only; ⊥ direct asyncpg/psycopg calls in `ui/`.
- V11. ETL pipeline: extract → validate schema → deduplicate → normalize → load; any step failure → job status=`failed` + error logged.
- V12. LLM-generated report ! appended to `chat_history`: `{id, user_id?, query, response, sources, created_at}`.
- V13. Chunker ! split text longer than `max_tokens` even when sentence delimiters are absent.
- V14. ∀ `/v1/*` endpoint ! rate-limited per IP (slowapi); 429 on exceed; default 200/min global.
- V15. `POST /v1/ingest/docs` ! reject URLs that resolve to private/reserved IPs (SSRF guard).
- V16. `POST /v1/ingest/upload` ! reject files > 10 MB with 413; `POST /v1/ingest/docs` ! reject docs > 10 MB on fetch.
- V17. API startup ! reject insecure `API_KEY` defaults and missing LLM key for active provider.
- V18. Auth comparison ! constant-time (`hmac.compare_digest`); ⊥ short-circuit string equality.
- V19. ML directional signal ! validated walk-forward (TimeSeriesSplit, no lookahead); promoted only on OOS edge; unpromoted model ⊥ contribute to any decision (weight effectively 0).
- V20. Symbol/SSRF/size validation ! run as a request dependency BEFORE `get_db`; invalid input → 422/413 without acquiring a DB connection.
- V21. Derived signals (regime, events, stops, drift, attribution, data-quality, ML inference) ! computed on read from stored data; only events (alerts) are persisted — ⊥ store derived state that can go stale.
- V22. Engine confidence caps (vol, earnings, regime, event) compose via `min()` — the most conservative cap always wins; adding a gate ⊥ raise confidence anywhere.

---

## §T Tasks

| id  | status | task                                                                                     | cites                        |
|-----|--------|------------------------------------------------------------------------------------------|------------------------------|
| T1  | .      | scaffold repo: `api/`, `ingest/`, `analytics/`, `retrieval/`, `rag/`, `scheduler/`, `ui/`, `tests/` | C2                  |
| T2  | .      | PostgreSQL schema: `stocks`, `market_data`, `financial_reports`, `embeddings`, `alerts`, `users`, `chat_history`, `jobs` | V1,V4,V8,V9,V12,I.db |
| T3  | x      | ETL ingest: yfinance + Finnhub → extract → validate → dedupe → upsert `market_data`    | C12,V4,V7,V8,V11,I.yf,I.fh  |
| T4  | .      | document ingestion: fetch financial docs → chunk → embed (SentenceTransformer) → upsert `financial_reports` + `embeddings` + update FAISS | V1,V2,C6,I.emb,I.vec |
| T5  | .      | analytics engine: SMA, EMA, RSI, volatility, momentum, Z-score anomaly → store results | V5,V9,C9                     |
| T6  | .      | anomaly detection: Isolation Forest + rolling thresholds on `market_data` → write `alerts` | V9,C9                     |
| T7  | .      | FAISS retrieval service: load index, `search(query_embedding, top_k)` → `[{doc_id, chunk_id, score}]` | V2,V3,I.vec |
| T8  | .      | RAG chain: embed query → FAISS search → fetch chunks from DB → LLM prompt → `{answer, sources}` | V3,V12,C10,I.llm,I.emb |
| T9  | .      | LLM reporting: scheduled sector summaries via LLM → store in `chat_history`            | V12,C10,C8,I.llm             |
| T10 | x      | FastAPI routers: `/v1/stocks`, `/v1/ingest`, `/v1/analytics`, `/v1/query`, `/v1/alerts`, `/v1/jobs`, `/v1/reports`, `/v1/decision`, `/v1/fundamentals`, `/v1/options` | V6,C5,I.api |
| T11 | x      | auth middleware: `X-API-Key` header → `hmac.compare_digest`; 401 on failure            | V6,C5,C7,V18                 |
| T12 | x      | APScheduler worker: 19 cron jobs (market_refresh, analytics_run, anomaly_scan, sentiment_run, india_signals_run, regime_run, decision_run, fundamentals_run, paper_auto_run, stops_run, data_quality_run, report_run, corporate_actions_run, signal_snapshot_run, weight_tuning_run, events_run, ml_train_run, doc_refresh) | C8,V8,I.sched |
| T13 | x      | Streamlit dashboard: 15 tabs (Market Overview, Live, Watchlist, Paper Trading, Analytics, Fundamentals, AI Insights, Decision Intelligence, Performance, Calibration, Options, Portfolio, RAG Chat, Knowledge Base, Jobs) | V10,C3,I.ui |
| T14 | x      | Docker Compose: `api`, `worker` (scheduler), `db` (postgres:16), `ui` (streamlit) services | C11                       |
| T15 | x      | integration tests: ETL roundtrip, RAG Q&A with citations, anomaly detection trigger, auth rejection | V3,V6,V7,V9,V11    |
| T16 | x      | EMA crossover (EMA9 vs EMA20) + volume confirmation signals; earnings proximity gate; 8 signals total; `ema_9` in analytics; weights rebalanced | C2,V5 |
| T17 | x      | Multi-agent decision explanation: Bull + Bear agents parallel (asyncio.gather) → Synthesis; `bull_case`/`bear_case` persisted to decisions table | C10,V12 |
| T18 | x      | Self-learning loop: recommendation accuracy (R-perf), confidence calibration + ECE/Brier, per-signal attribution (R3), random-simplex weight tuning auto-promoted on OOS (R4), drift monitoring + alerts (R7) | V8,V9 |
| T19 | x      | Position sizing (R2): half-Kelly + vol-target + risk-budget → most conservative, calibrated win-prob; `position_sizing` in decision response | V5 |
| T20 | x      | Paper trading (R1): pure engine (avg-cost, realized P&L, CostModel), auto-exec from decisions, equity curve + Sharpe/drawdown; migrations 010/013 | V8 |
| T21 | x      | Cost-realistic backtest (P2): next-bar-open fills + market-aware CostModel; net/gross/cost-drag; capital/discrete mode. ⛔ survivorship bias data-blocked | — |
| T22 | x      | India signals (P5): FII/DII + NIFTY PCR + Gift Nifty → `india_flow` overlay (.NS/.BO only); migration 014; `india_signals_run` | I.yf |
| T23 | x      | Corporate actions (P6): split/dividend capture + explicit `auto_adjust` ingest; migration 009 | V4 |
| T24 | x      | Market regime (R5): Bull/Bear/High-Vol/Sideways per market; regime-tilted weights + high-vol cap; migration 015; `regime_run` | V5 |
| T25 | x      | Portfolio risk (R6): sector/country/cap concentration (HHI) + correlation + historical VaR/CVaR + risk score; `GET /v1/portfolio/risk` | — |
| T26 | x      | Drift monitoring (R7) + per-call attribution (R9): rolling accuracy, drift verdict + alerts, return decomposition by signal | V9 |
| T27 | x      | Investment committee (R10): Technical/Fundamental/Macro/Sentiment ‖ + Risk Officer deterministic veto; `committee_json`; migration 016 | C10,V12 |
| T28 | x      | Macro event gate (R8): FOMC/RBI/Budget/CPI calendar + confidence gate per market; migration 017; `events_run` | — |
| T29 | x      | Stop-loss / trailing stops (P3): vol-derived stops per position + breach alerts; migration 018; `stops_run`; `GET/PUT /v1/portfolio/stops` | V9 |
| T30 | x      | Multi-timeframe confluence (P8): daily/weekly/monthly (resampled) + intraday; `GET /v1/decision/{symbol}/timeframes` | V5 |
| T31 | x      | Data reliability (P9): OHLC consistency + outliers (split/circuit-aware) + staleness + reconciliation; `data_quality_run`; `GET /v1/data-quality/{symbol}` | V4,V9 |
| T32 | x      | ML directional signal (P14): sklearn GBM on as-of features, walk-forward OOS, promote-on-edge gate; `ml` overlay signal; migration 019; `ml_train_run`; `GET /v1/ml/model` | V5,V19 |

---

## §B Bug Log

| id | date | cause | fix |
|----|------|-------|-----|
| B1 | 2026-05-14 | chunker only flushed on sentence boundaries; delimiterless long text stayed one chunk | V13 |
| B2 | 2026-05-23 | auth used `==` string comparison; vulnerable to timing attack | V18; `hmac.compare_digest` |
| B3 | 2026-05-23 | anomaly_scan and analytics_run shared same cron; fired simultaneously | D45; dedicated `anomaly_scan_cron` at :30 |
| B4 | 2026-05-23 | chunker used `len(text.split())` word count; undercounted tokens ~4× | D46; char/4 heuristic |
| B5 | 2026-05-23 | FAISS global state unprotected from concurrent access; no lock | D47; `threading.Lock` + `os.replace` |
| B6 | 2026-05-23 | LLM calls had no timeout; stalled call blocked event loop indefinitely | D48; 30s `asyncio.wait_for` + retry |
| B7 | 2026-05-23 | `decision_run` propagated first symbol exception, skipping all remaining symbols | D49; per-symbol try/except |
| B8 | 2026-05-23 | `sentiment_run` wrote `status="success"` (not in allowed enum); job shown as failed in UI | fixed to `"completed"` |
| B9 | 2026-05-23 | `POST /v1/ingest/docs` no URL validation; SSRF to internal services possible | V15; `validate_ingest_url()` |
| B10 | 2026-05-23 | file upload had no size cap; large PDF would OOM api container | V16; 10 MB hard limit, 413 on exceed |
| B11 | 2026-05-23 | `sector_report.py` and `ingest/documents.py` silently swallowed all exceptions | D49; logged warning + continue |
| B12 | 2026-05-23 | Prophet `model.fit()` could run on <10 rows causing cryptic exception; no timeout | D48; ≥10 row guard + 60s timeout |
| B13 | 2026-05-23 | `GET /v1/reports` had no pagination (hardcoded LIMIT 20, no offset) | V14; `limit`/`offset` query params |
| B14 | 2026-05-23 | `sector_report` had no REST endpoint; only reachable via scheduler | added `POST /v1/reports/generate` |
| B15 | 2026-06-01 | `build_decision_prompt` f-string `${predicted_close:.2f if predicted_close else 'N/A'}` — format spec after `:` cannot contain conditional; raises `ValueError` at runtime | extracted to `forecast_str`/`current_str` locals before f-string |
| B16 | 2026-06-01 | `_render_comparison` in decision_intelligence.py used `"Current Price"` key in success rows but `"Price"` in error rows + formatting; `KeyError: 'Price'` at runtime | unified all rows to `"Price"` key |
| B17 | 2026-06-01 | 9 Streamlit buttons across 6 files had no explicit `key=` param; auto-generated keys unstable on layout changes | added unique keys to all buttons |
| B18 | 2026-06-10 | validation ran in endpoint bodies AFTER `Depends(get_db)`; invalid symbol/SSRF/oversize returned 500 (not 422/413) when the pool was down | V20; `validated_symbol` + SSRF/size as pre-DB dependencies |
| B19 | 2026-06-10 | `analytics_run` + analytics-router computed `ema_9` then dropped it from the persisted column list → ema_crossover signal permanently null | added `ema_9` to both upsert column lists; backfilled |
| B20 | 2026-06-10 | `analytics_run`/`anomaly_scan` read symbols from raw `os.getenv` (5-symbol fallback) not `settings.tracked_symbols`; `datetime.utcnow()` deprecated | switched to settings + tz-aware now |
| B21 | 2026-06-10 | `decision_run` had drifted to the v1 6-signal engine (no ema/volume/earnings gate, hardcoded weights) — nightly cached decisions disagreed with API | brought to parity: ema/volume/days_to_earnings + active tuned weights |
| B22 | 2026-06-10 | `anomaly_scan`/`analytics` did `Decimal - float` math on asyncpg NUMERIC rows → TypeError (recurred in portfolio risk via `get_prices_multi`) | coerce numeric DataFrame columns with `.astype(float)` at every asyncpg→pandas boundary |
| B23 | 2026-06-10 | sentiment aggregates return rows with NULL score (`NULLIF(SUM(count),0)`); `float(None)` 500'd the decision endpoint + decision_run | guard `score is not None` at all consumption sites |
| B24 | 2026-06-11 | Google retired `gemini-1.5-flash` → every LLM call 404'd; `_safe_complete` masked it as silently empty bull/bear/reports/committee | `LLM_MODEL=gemini-2.5-flash` + `--force-recreate` (env_file reload) |
| B25 | 2026-06-17 | named a column `trailing` — a reserved SQL keyword — so migration 018 DDL aborted and took the whole API container down on startup | renamed to `is_trailing` |
| B26 | 2026-06-17 | `datetime` is a subclass of `date`; `_as_date` returned the datetime unchanged → ML feature/label date keys never matched → empty dataset | check `isinstance(v, datetime)` first and call `.date()` |
| B27 | 2026-06-18 | `get_sentiment_by_date_range` did `float(score)` on the count-weighted aggregate which can be NULL → **live 500 on `/v1/decision/backtest/{symbol}`** (recurrence of the B23 float(None) class) | guard `if r["score"] is not None`; regression test added |
| B28 | 2026-06-18 | P9 circuit-band classification was dead code — bands (≤20%) could never exceed the 35% outlier gate, so the India circuit-breaker feature never fired | detect circuit bands (10%/20%) independently below the outlier gate; classified informational, not counted as a data issue |
| B29 | 2026-06-18 | React frontend Backtesting read `net_return`/`equity_curve[].equity`, but the default daily backtest returns `total_return`/`{date, cumulative}` → blank metric + empty chart | frontend normalizes both shapes (`net_return ?? total_return`, `equity ?? cumulative`) |
