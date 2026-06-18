# Finance AI Engine

> Enterprise-grade AI financial-intelligence platform for **US + Indian equities** — a self-learning, multi-signal decision engine with regime/macro awareness, an ML directional model, portfolio risk + stop-loss tracking, a multi-agent investment committee, RAG document Q&A, paper trading, and a closed MLOps feedback loop.

<p>
<img alt="Python" src="https://img.shields.io/badge/python-3.12-blue">
<img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-009688">
<img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16-336791">
<img alt="FAISS" src="https://img.shields.io/badge/FAISS-vector%20search-orange">
<img alt="Docker" src="https://img.shields.io/badge/Docker-Compose-2496ED">
</p>

**Two frontends, one API:** a modern **React + Vite + TypeScript** console (`frontend-react/`) and a 15-tab **Streamlit** dashboard (`frontend/`) — both talk only to the FastAPI `/v1/*` API, so they're interchangeable clients.

---

## Features

| Feature | Details |
|---------|---------|
| Live market data | yfinance + Finnhub API; 709 symbols (310 US + 399 NSE) |
| Technical analytics | SMA, EMA9/EMA20, RSI, Volatility, Momentum (persisted to `analytics`) |
| Anomaly detection | Z-score, Isolation Forest, rolling thresholds → `alerts` |
| Multi-source sentiment | FinBERT on 6 sources: Yahoo Finance, Google News, StockTwits, Reddit, Global News (Reuters/CNBC/MarketWatch), India News (MoneyControl/ET/LiveMint); count-weighted, cross-source deduped |
| Price forecasting | Prophet 7-day forecast with 80% confidence intervals |
| Decision engine v2 | BUY/SELL/HOLD — 8-signal graduated scoring (5 levels), EMA crossover, volume confirmation, earnings gate, consensus boost, extreme-vol cap |
| **Market regime (R5)** | Daily Bull/Bear/High-Vol/Sideways per market (SPY+VIX / NIFTY+India VIX + breadth); regime-tilted signal weights + high-vol confidence cap |
| **Macro event gate (R8)** | FOMC / RBI MPC / Budget / CPI calendar; confidence gated ahead of high-impact events (per market; GLOBAL gates both) |
| **ML directional signal (P14)** | Gradient-boosted trees (sklearn) on engineered features; walk-forward OOS validated; appended only when it beats the promotion gate — earns its weight or stays silent |
| **Position sizing (R2)** | Half-Kelly + vol-target + risk-budget → most conservative, calibrated win-probability |
| **Stop-loss / trailing stops (P3)** | Vol-derived trailing/fixed stops per position; breach alerts |
| **Portfolio risk (R6)** | Sector/country/cap concentration (HHI) + correlation + historical VaR/CVaR + 0–100 risk score |
| **Dynamic weight tuning (R4)** | Self-learning random-simplex optimizer; net-of-cost, expanding-window CV; auto-promotes only on out-of-sample gain |
| **Confidence calibration + drift (R7)** | Reliability curve + ECE/Brier; per-signal edge & attribution; model-health drift verdict + alerts |
| **Per-call attribution (R9)** | Each closed call's realized return decomposed by signal |
| **Multi-agent committee (R10)** | Technical / Fundamental / Macro / Sentiment specialists in parallel + Risk Officer with deterministic veto |
| **India market signals (P5)** | FII/DII flow + NIFTY PCR (contrarian) + Gift Nifty → `india_flow` overlay (.NS/.BO only) |
| **Corporate actions (P6)** | Split/dividend capture; explicit `auto_adjust` ingest |
| **Multi-timeframe confluence (P8)** | Daily + weekly + monthly (resampled) + optional 1h intraday; cross-horizon agreement verdict |
| **Data reliability (P9)** | OHLC consistency, return outliers (split + India-circuit aware), staleness, live-quote reconciliation |
| Backtesting (cost-realistic) | Next-bar-open fills, market-aware cost model, net/gross/cost-drag, capital mode |
| Paper trading | Virtual portfolio vs real prices; auto-exec from decisions; equity curve + Sharpe/drawdown |
| Watchlist + live P&L | Persisted holdings enriched with price, P&L, decision, sentiment, suggested size |
| Recommendation accuracy | Scores past BUY/SELL/HOLD vs realized price; hit rate by rec/risk |
| Real-time stream | WebSocket `/v1/stream` — live quotes + decisions + alerts pushed every 5s |
| Fundamental analysis | P/E, EPS, margins, analyst target, 52W range, earnings calendar, sector |
| Options chain | Live calls & puts via yfinance |
| Portfolio optimization | Mean-variance optimizer (scipy SLSQP) |
| RAG assistant | FAISS + Sentence Transformers + Gemini/OpenAI |
| Document ingestion | PDF, CSV, XLSX, TXT, JSON, HTML — URL or file upload |
| AI sector reports | LLM-generated summaries, scheduled daily |
| REST API | FastAPI `/v1/*` with API-key auth and rate limiting |
| Background jobs | 19 APScheduler cron jobs with retry + exponential backoff |
| React console | `frontend-react/` — Vite + TypeScript (strict) + Tailwind; Overview, Portfolio, AI Recommendations, Risk (incl. paper-trade ticket), Backtesting, Market Signals, Reports, Settings; accessible + responsive, route-level code-split |
| Streamlit dashboard | `frontend/` — 15-tab UI with Plotly charts |
| Deployment | Docker Compose — 4 services, health-checked, resource-limited |

---

## Architecture

```
yfinance / Finnhub / RSS + social
      ↓
ETL Pipeline (validate → dedupe → upsert)        Document ingest → FAISS
      ↓                                                  ↓
PostgreSQL 16 ── analytics ── 6-source FinBERT     RAG Chain (Gemini/OpenAI)
      ↓          sentiment   Prophet forecast            ↓
Market Regime (R5) · Macro Events (R8) · India Signals (P5)   Document Q&A
      ↓
Decision Engine (8 signals + regime tilt + event gate + ML overlay + india overlay)
      ↓
Position Sizing (R2) · Stop-Loss (P3) · Portfolio Risk (R6)
      ↓
Multi-Agent Committee (Technical/Fundamental/Macro/Sentiment ‖ → Risk Officer veto)
      ↓
FEEDBACK LOOP: performance → calibration → drift (R7) → weight tuning (R4) → engine
      ↓
FastAPI /v1/* REST API  +  WebSocket /v1/stream
      ↓
Streamlit Dashboard (15 tabs)  ·  Paper Trading  ·  Watchlist
```

**Services (Docker Compose):**

| Service | Role | Memory | CPU |
|---------|------|--------|-----|
| `db` | PostgreSQL 16 | 1 GB | 1 |
| `api` | FastAPI + uvicorn | 2 GB | 2 |
| `worker` | APScheduler (19 cron jobs) | 4 GB | 2 |
| `ui` | Streamlit dashboard | 512 MB | 1 |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Backend | FastAPI + uvicorn |
| Database | PostgreSQL 16 (asyncpg) |
| Vector store | FAISS (IndexFlatIP, dim=384) |
| Embeddings | Sentence Transformers `all-MiniLM-L6-v2` |
| LLM | Gemini 2.5 Flash / OpenAI GPT-4o-mini |
| Sentiment | FinBERT (`ProsusAI/finbert`) + StockTwits native labels |
| ML | scikit-learn HistGradientBoostingClassifier (walk-forward, TimeSeriesSplit) |
| Forecasting | Prophet (7-day, asyncio timeout) |
| Market data | yfinance (OHLCV, fundamentals, options, intraday) + Finnhub (live quotes) |
| Scheduler | APScheduler 3.x AsyncIOScheduler |
| Real-time | FastAPI/Starlette WebSocket |
| Rate limiting | slowapi (per-IP, per-endpoint) |
| Logging | python-json-logger (structured JSON + request IDs) |
| Dashboard | Streamlit + Plotly |
| Deployment | Docker Compose |

---

## Decision Engine

8 core signals with 5-level graduated scoring (−1.0 / −0.5 / 0.0 / +0.5 / +1.0):

| Signal | Weight | Bullish (+0.5/+1.0) | Bearish (−0.5/−1.0) |
|--------|--------|---------------------|---------------------|
| RSI | 0.12 | < 35 / < 25 | > 65 / > 75 |
| Trend (close vs SMA-20) | 0.16 | above / > +3% | below / < −3% |
| Momentum (10-period) | 0.12 | > +2% / > +5% | < −2% / < −5% |
| Volatility (20-day ann.) | 0.08 | < 0.25 / < 0.15 | > 0.35 / > 0.45 |
| **Sentiment** | **0.22** | > 0.15 / > 0.40 | < −0.15 / < −0.30 |
| Forecast (Prophet 7-day) | 0.12 | > +1% / > +3% | < −1% / < −3% |
| **EMA Crossover** (EMA9 vs EMA20) | **0.10** | gap > +0.5% / > +2% | gap < −0.5% / < −2% |
| **Volume Confirmation** | **0.08** | high vol + rising | high vol + falling |

- BUY if weighted sum ≥ **0.30**; SELL if ≤ **−0.30**; else HOLD.
- Consensus boost: 6+ of 8 agree → confidence × 1.15 (cap 0.99). Extreme-vol cap: vol > 0.55 → ≤ 0.70.
- **Earnings gate**: ≤ 7d → ≤ 0.65; ≤ 14d → ≤ 0.80. **Event gate (R8)**: high-impact ≤ 1d → ≤ 0.60, ≤ 3d → ≤ 0.75. **Regime cap (R5)**: high-vol regime → ≤ 0.75. (Most conservative cap wins.)

**Overlay signals** (kept off the 8-weight vector so tuning/calibration are untouched; appended conditionally):
- **`india_flow`** (weight 0.10) — `.NS`/`.BO` only: FII/DII + PCR + Gift Nifty.
- **`ml`** (weight 0.10) — only when a promoted ML model returns a probability.
- **Regime-tilted weights** — in a known regime the 8 base weights are tilted (momentum-following in bull, mean-reversion in sideways) and renormalized.

## Multi-Agent Committee (R10)

Four specialists run in parallel (`asyncio.gather`), each with a domain-sliced context: **Technical** (price action), **Fundamental** (multiples), **Macro** (regime + vol), **Sentiment** (crowd). A **Risk Officer** then writes a narrative — but the **veto is deterministic code**, not LLM output: a BUY/SELL flips to HOLD when vol > 0.55, the regime is high-vol, or earnings are ≤ 3 days out. Verdict persisted to `decisions.committee_json`. (Bull/Bear/Synthesis explanation runs on every decision; the committee is on-demand.)

## Self-Learning Loop (R3 / R4 / R7)

Decisions → realized outcomes → **calibration** (reliability curve, ECE/Brier) → **per-signal attribution** (which signals earned the return) → **weight tuning** (random-simplex, net-of-cost, expanding-window CV, auto-promote only on out-of-sample gain) → engine. **Drift monitoring** compares recent vs baseline accuracy and alerts on decay.

---

## Quickstart

### Prerequisites
- Docker + Docker Compose
- Gemini or OpenAI API key
- Finnhub API key (free tier works)

### 1. Clone and configure

```bash
git clone https://github.com/Rupin-Gupta/Finance-AI-Engine.git
cd Finance-AI-Engine
cp .env.example .env
```

Edit `.env`:
```env
POSTGRES_PASSWORD=your-secure-password
API_KEY=your-secret-api-key
LLM_PROVIDER=gemini            # or openai
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your-gemini-key
FINNHUB_API_KEY=your-finnhub-key
# Leave TRACKED_SYMBOLS unset to track all 709 symbols
# TRACKED_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,TSLA   # optional subset
```

### 2. Launch

```bash
docker compose up --build
```

Services start in order: `db` → `api` → `worker` → `ui`

### 3. Bootstrap market data

```bash
curl -X POST http://localhost:8000/v1/ingest/market \
  -H "X-API-Key: your-secret-api-key" -H "Content-Type: application/json" \
  -d '{"symbols":["AAPL","MSFT","RELIANCE.NS"],"period":"1y","interval":"1d"}'
```
Then trigger `analytics_run`, `sentiment_run`, `fundamentals_run`, `regime_run`, `events_run`, `decision_run` (via `POST /v1/jobs/trigger/{job}`) or let the daily crons run.

### 4. Open a frontend

- **Streamlit dashboard:** http://localhost:8501 (runs in the `ui` container)
- **React console:** see "Local development" below (run separately against the API)

---

## Local Development

Run the backend in Docker and the **React console** on your host for fast HMR:

```bash
# 1. Backend (api on :8000, db, worker) — UI optional
docker compose up db api worker

# 2. React console
cd frontend-react
npm install          # first time only (node_modules is git-ignored)
npm run dev          # http://localhost:5173
```

The Vite dev server proxies `/v1`, `/health`, and `/ready` to the API on `:8000`, so the browser stays same-origin (no CORS, no API key in the client). It binds IPv4 loopback (`server.host = "127.0.0.1"` in `vite.config.ts`) — if `localhost:5173` ever refuses, use `http://127.0.0.1:5173`.

```bash
npm run build        # type-check (tsc strict) + production bundle
npm run typecheck    # types only
```

**Tests (backend):**
```bash
pytest                      # full suite
pytest tests/unit           # pure-core unit tests
```

---

## API Reference

All `/v1/*` endpoints require the `X-API-Key` header.

### Market Data & Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/ingest/market` | Ingest OHLCV |
| GET | `/v1/stocks/{symbol}/quote` · `/ohlcv` | Quote (Finnhub→DB) · historical OHLCV |
| GET | `/v1/analytics/{symbol}` | SMA/EMA/RSI/vol/momentum |
| GET | `/v1/alerts` | Anomaly + drift + stop-breach + data-quality alerts |
| GET | `/v1/data-quality/{symbol}` | Reliability report (consistency, outliers, staleness, reconcile) |

### Decision Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/decision/{symbol}` | Full payload: rec, signals, regime, event gate, sizing, forecast, sentiment, bull/bear/synthesis |
| GET | `/v1/decision/{symbol}/committee` | Investment committee (4 specialists + Risk Officer veto) |
| GET | `/v1/decision/{symbol}/timeframes` | Daily/weekly/monthly (+intraday) confluence |
| GET | `/v1/decision/backtest/{symbol}?days=N` | Cost-realistic backtest (capital mode via `hold_days`/`capital`) |

### Regime · Events · India · ML
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/regime` · `/regime/history` | Market regime per market (US/INDIA) |
| GET | `/v1/events` | Upcoming macro events (FOMC/RBI/Budget/CPI) |
| GET | `/v1/india/signals` · `/india/deals/{symbol}` | FII/DII + PCR + Gift Nifty · bulk deals |
| GET | `/v1/ml/model` | Active/latest ML model + OOS metrics |

### Portfolio · Risk · Stops · Paper
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/portfolio/optimize` | Mean-variance optimization |
| GET | `/v1/portfolio/risk?source=watchlist\|paper` | Concentration + correlation + VaR/CVaR + risk score |
| GET | `/v1/portfolio/stops?source=watchlist\|paper` | Stop-loss / trailing-stop monitor + breaches |
| PUT | `/v1/portfolio/stops/{symbol}` | Set/override a symbol's stop config |
| GET/POST/DELETE | `/v1/watchlist` | Holdings with live P&L + suggested size |
| GET | `/v1/paper` · `/paper/history` · POST `/paper/trade` · `/reset` | Paper portfolio + equity curve |

### Performance · Calibration · Weights
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/performance` · `/performance/attribution` | Accuracy tracker · per-call signal attribution |
| GET | `/v1/calibration` · `/calibration/history` · `/calibration/drift` | Reliability + signal edge · trend · model drift |
| GET | `/v1/weights` | Default vs auto-tuned signal weights |

### Fundamentals · Options · Corporate Actions · RAG · Reports · Jobs · Stream
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/fundamentals/{symbol}` · `/v1/options/{symbol}` · `/v1/corporate-actions/{symbol}` | |
| POST | `/v1/ingest/docs` · `/v1/ingest/upload` · `/v1/query` | RAG ingest + Q&A |
| GET/POST | `/v1/reports` · `/reports/generate` | AI sector reports |
| GET/POST | `/v1/jobs` · `/jobs/{id}` · `/jobs/trigger/{job}` | Job status + manual trigger |
| WS | `/v1/stream?api_key=...` | Live quotes + decisions + alerts |
| GET | `/health` · `/ready` | Liveness · readiness |

**Interactive docs:** http://localhost:8000/docs

---

## Background Jobs

19 cron jobs run in the `worker` container (all job-tracked + retried with exponential backoff):

| Job | Schedule | Description |
|-----|----------|-------------|
| `market_refresh` | Daily 18:00 wd | Latest OHLCV |
| `analytics_run` | Hourly :00 wd | SMA/EMA/RSI/vol/momentum |
| `anomaly_scan` | Hourly :30 wd | Anomaly detection |
| `regime_run` | Daily 08:05 wd | Market regime classification (R5) |
| `sentiment_run` | Daily 08:00 wd | 6-source FinBERT sentiment |
| `india_signals_run` | Daily 08:15 wd | FII/DII + PCR (P5) |
| `decision_run` | Daily 08:30 wd | Full decision pipeline |
| `fundamentals_run` | Daily 09:00 wd | P/E, EPS, margins, sector |
| `paper_auto_run` | Daily 10:00 wd | Auto-exec paper trades (opt-in) |
| `stops_run` | Daily 16:00 wd | Stop-loss breach scan (P3) |
| `data_quality_run` | Daily 17:30 wd | Data reliability scan (P9) |
| `report_run` | Daily 19:00 wd | LLM sector summaries |
| `corporate_actions_run` | Weekly Sat 03:00 | Splits/dividends (P6) |
| `signal_snapshot_run` | Weekly Sat 04:00 | Signal-edge history + calibration cache + drift alert |
| `weight_tuning_run` | Weekly Sat 04:30 | Walk-forward weight auto-tune (R4) |
| `events_run` | Weekly Sat 05:00 | Macro event calendar refresh (R8) |
| `ml_train_run` | Weekly Sat 06:00 | ML retrain + promote-on-edge (P14) |
| `doc_refresh` | Weekly Sun 02:00 | Re-ingest tracked URLs |

```bash
curl -X POST http://localhost:8000/v1/jobs/trigger/decision_run -H "X-API-Key: your-secret-api-key"
```

---

## Dashboard Tabs (15)

Market Overview (+ regime badges) · Live (WebSocket) · Watchlist · Paper Trading · Analytics · Fundamentals · AI Insights · **Decision Intelligence** (comparison, scorecard, committee, multi-timeframe, backtest, data-quality) · Performance (+ per-call attribution) · Calibration (+ drift + tuned weights + ML status) · Options Chain · Portfolio (+ risk + stop-loss monitor) · RAG Chat · Knowledge Base · Jobs.

---

## Security

- API key auth with timing-safe comparison (`hmac.compare_digest`); validation runs as a dependency **before** any DB access (invalid input → 422 without touching the pool).
- Rate limiting: 200/min global; tighter per-endpoint (5/min committee + backtest, 20/min decision, 30/min RAG, 5–10/min ingest).
- SSRF protection on document URL ingestion (blocks private IPs); 10 MB upload cap.
- Startup validation rejects insecure default keys + missing LLM key.
- Secrets via `.env` only — never committed.

---

## Project Structure

```
backend/
├── api/routers/   stocks, ingest, analytics, query, alerts, jobs, reports, decision,
│                  fundamentals, options, portfolio, watchlist, performance, calibration,
│                  corporate_actions, paper, weights, india, regime, events, data_quality, ml, stream
├── data/          US_SYMBOLS (310) + INDIA_SYMBOLS (399) = ALL_SYMBOLS (709)
├── ingest/        Market + document ETL; india_signals; events calendar
├── analytics/     indicators, anomaly, backtest, fundamentals, portfolio, portfolio_risk,
│                  performance, calibration, sizing, paper_trading, weight_tuning,
│                  corporate_actions, regime, events, stops, data_quality, timeframes
├── ml/            features (no-lookahead), model (GBM + walk-forward), inference (P14)
├── sentiment/     FinBERT + 6-source fetchers
├── decision/      signals (8 + overlays), engine, forecast, india_signals
├── rag/           chunker, embedder, FAISS store, retriever, chain
├── llm/           client (Gemini/OpenAI), multi_agent (Bull/Bear/Synthesis), committee (R10)
├── reporting/     LLM sector reports
├── db/            asyncpg pool + 19 migrations + per-domain query modules
└── scheduler/     APScheduler worker + 19 cron jobs

frontend/        Streamlit: app.py (15-tab router) + api_client.py + page_modules/
frontend-react/  React + Vite + TS console: src/pages/, src/components/, src/lib/ (proxies /v1 → :8000)

tests/     unit/ (pure cores + frontend smoke) + integration/ (API)
```

---

## Environment Variables

See `.env.example`. Key variables: `POSTGRES_PASSWORD`, `API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY` / `OPENAI_API_KEY`, `FINNHUB_API_KEY`, `TRACKED_SYMBOLS` (unset = all 709), `CORS_ORIGINS`, `PAPER_AUTO_TRADE_ENABLED`.
