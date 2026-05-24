# Finance AI Engine

An enterprise-grade AI-powered financial intelligence and market analytics platform. Combines real-time stock data, machine learning, RAG-based document Q&A, and a multi-signal decision engine into a production-ready system.

---

## Features

| Feature | Details |
|---------|---------|
| Live market data | yfinance + Finnhub API |
| Technical analytics | SMA, EMA, RSI, Volatility, Momentum |
| Anomaly detection | Z-score, Isolation Forest, rolling thresholds |
| Sentiment analysis | FinBERT on Yahoo Finance RSS headlines |
| Price forecasting | Prophet 7-day forecast with 80% confidence intervals |
| Decision engine | BUY/SELL/HOLD with 6-signal weighted scoring + AI explanation |
| RAG assistant | FAISS + Sentence Transformers + Gemini/OpenAI |
| Document ingestion | PDF, CSV, XLSX, TXT, JSON, HTML — URL or file upload |
| AI sector reports | LLM-generated summaries, scheduled daily |
| REST API | FastAPI `/v1/*` with API-key auth and rate limiting |
| Background jobs | 7 APScheduler cron jobs with retry and exponential backoff |
| Dashboard | 7-tab Streamlit UI with Plotly charts |
| Deployment | Docker Compose — 4 services, health-checked, resource-limited |

---

## Architecture

```
yfinance / Finnhub
      ↓
ETL Pipeline (validate → dedupe → upsert)
      ↓
PostgreSQL 16                    FAISS Vector Index
      ↓                                ↓
Analytics Engine              RAG Chain (Gemini/OpenAI)
FinBERT Sentiment                      ↓
Prophet Forecasting           Document Q&A
      ↓
Decision Engine (6-signal weighted scoring)
      ↓
FastAPI /v1/* REST API
      ↓
Streamlit Dashboard (7 tabs)
```

**Services (Docker Compose):**

| Service | Role | Memory | CPU |
|---------|------|--------|-----|
| `db` | PostgreSQL 16 | 1 GB | 1 |
| `api` | FastAPI + uvicorn | 2 GB | 2 |
| `worker` | APScheduler (7 cron jobs) | 4 GB | 2 |
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
| LLM | Gemini 1.5 Flash / OpenAI GPT-4o-mini |
| Sentiment | FinBERT (`ProsusAI/finbert`) |
| Forecasting | Prophet (7-day, asyncio timeout) |
| Scheduler | APScheduler 3.x AsyncIOScheduler |
| Rate limiting | slowapi (per-IP, per-endpoint) |
| Logging | python-json-logger (structured JSON + request IDs) |
| Dashboard | Streamlit + Plotly |
| Deployment | Docker Compose |

---

## Decision Engine

6 signals scored -1 / 0 / +1 with configurable weights:

| Signal | Weight | Bullish | Bearish |
|--------|--------|---------|---------|
| RSI | 0.20 | < 35 (oversold) | > 65 (overbought) |
| Trend (close vs SMA-20) | 0.20 | above | below |
| Momentum (10-period) | 0.15 | > +2% | < -2% |
| Volatility (20-day ann.) | 0.15 | < 0.25 | > 0.45 |
| Sentiment (FinBERT) | 0.15 | > 0.3 | < -0.2 |
| Forecast (Prophet 7-day) | 0.15 | predicted > current +1% | predicted < current -1% |

Weighted sum ≥ 0.35 → **BUY** | ≤ -0.35 → **SELL** | else → **HOLD**

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
LLM_PROVIDER=gemini          # or openai
GEMINI_API_KEY=your-gemini-key
FINNHUB_API_KEY=your-finnhub-key
TRACKED_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,TSLA
```

### 2. Launch

```bash
docker compose up --build
```

Services start in order: `db` → `api` → `worker` → `ui`

### 3. Ingest market data

```bash
curl -X POST http://localhost:8000/v1/ingest/market \
  -H "X-API-Key: your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{"symbols":["AAPL","MSFT","GOOGL","AMZN","TSLA"],"period":"3mo","interval":"1d"}'
```

### 4. Open dashboard

http://localhost:8501

---

## API Reference

All endpoints require `X-API-Key` header.

### Market Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/ingest/market` | Ingest OHLCV from yfinance + Finnhub |
| GET | `/v1/stocks/{symbol}/quote` | Latest quote (Finnhub → DB fallback) |
| GET | `/v1/stocks/{symbol}/ohlcv` | Historical OHLCV |
| GET | `/v1/analytics/{symbol}` | Technical indicators |
| GET | `/v1/alerts` | Anomaly detection alerts |

### Decision Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/decision/{symbol}` | BUY/SELL/HOLD + signals + forecast + explanation |
| GET | `/v1/decision/{symbol}?force=true` | Bypass 4-hour cache, recompute |

### Documents & RAG
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/ingest/docs` | Ingest document by URL |
| POST | `/v1/ingest/upload` | Upload file (PDF/CSV/XLSX/TXT, max 10 MB) |
| POST | `/v1/query` | RAG Q&A with citations |

### Reports & Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/reports` | AI-generated sector reports (paginated) |
| POST | `/v1/reports/generate` | Generate reports on demand |
| GET | `/v1/jobs/{job_id}` | Job status |
| POST | `/v1/jobs/trigger/{job_name}` | Trigger scheduler job manually |

### Ops
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (DB connectivity + pool stats) |

**Interactive docs:** http://localhost:8000/docs

---

## Background Jobs

7 cron jobs run in the `worker` container:

| Job | Schedule | Description |
|-----|----------|-------------|
| `market_refresh` | Daily 18:00 (weekdays) | Fetch latest OHLCV |
| `analytics_run` | Hourly :00 (weekdays) | Compute indicators |
| `anomaly_scan` | Hourly :30 (weekdays) | Detect anomalies |
| `sentiment_run` | Daily 08:00 (weekdays) | FinBERT headline scoring |
| `decision_run` | Daily 08:30 (weekdays) | Full decision pipeline |
| `report_run` | Daily 19:00 (weekdays) | LLM sector summaries |
| `doc_refresh` | Weekly Sun 02:00 | Re-ingest tracked URLs |

Trigger any job manually:
```bash
curl -X POST http://localhost:8000/v1/jobs/trigger/decision_run \
  -H "X-API-Key: your-secret-api-key"
```

---

## Security

- API key auth with timing-safe comparison (`hmac.compare_digest`)
- Rate limiting: 200/min global; 20/min decision; 30/min RAG; 5–10/min ingest
- SSRF protection on document URL ingestion (blocks private IP ranges)
- 10 MB upload size cap
- Startup validation rejects insecure default keys
- Secrets via `.env` only — never committed

---

## Project Structure

```
backend/
├── api/          FastAPI routers, auth, rate limiting, validators
├── ingest/       Market data + document ETL pipelines
├── analytics/    Technical indicators + anomaly detection
├── sentiment/    FinBERT pipeline + Yahoo RSS fetcher
├── decision/     Signal scoring + Prophet forecasting + engine
├── rag/          Chunker + embedder + FAISS store + RAG chain
├── llm/          LLM client (Gemini/OpenAI) with timeout + retry
├── reporting/    LLM sector report generation
├── db/           asyncpg pool + migrations + query modules
└── scheduler/    APScheduler worker + 7 cron jobs

frontend/
├── app.py                  Streamlit tab router (7 tabs)
├── api_client.py           HTTP client (sole UI→API interface)
└── page_modules/           One file per dashboard tab

tests/
├── unit/                   Chunker, indicators
└── integration/            API endpoint tests
```

---

## Environment Variables

See `.env.example` for all variables with descriptions.

Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `API_KEY` | Yes | Auth key for all `/v1/*` endpoints |
| `LLM_PROVIDER` | Yes | `gemini` or `openai` |
| `GEMINI_API_KEY` | If gemini | Google AI Studio key |
| `OPENAI_API_KEY` | If openai | OpenAI key |
| `FINNHUB_API_KEY` | Yes | Finnhub market data key |
| `TRACKED_SYMBOLS` | Yes | Comma-separated symbols, e.g. `AAPL,MSFT` |
| `CORS_ORIGINS` | Yes | Comma-separated origins (use `*` for dev only) |
