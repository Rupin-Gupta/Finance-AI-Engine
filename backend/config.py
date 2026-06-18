from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_tracked_symbols() -> str:
    from backend.data.symbols import ALL_SYMBOLS
    return ",".join(ALL_SYMBOLS)

_INSECURE_API_KEYS = {"changeme", "changeme-replace-in-production", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/finance"

    # FAISS
    faiss_index_path: str = "data/faiss.index"
    faiss_metadata_path: str = "data/faiss_meta.pkl"

    # LLM
    llm_provider: str = "openai"  # "openai" | "gemini"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Embeddings — dim=384 for all-MiniLM-L6-v2; changing model requires FAISS index rebuild
    embedding_model: str = "all-MiniLM-L6-v2"

    # Market data
    finnhub_api_key: str = ""

    # Auth
    api_key: str = "changeme"

    # Scheduler
    market_refresh_cron: str = "0 18 * * 1-5"    # daily after market close
    analytics_refresh_cron: str = "0 * * * 1-5"  # hourly on weekdays
    anomaly_scan_cron: str = "30 * * * 1-5"       # hourly on weekdays (30min offset from analytics)
    doc_refresh_cron: str = "0 2 * * 0"           # weekly Sunday 2am
    report_refresh_cron: str = "0 19 * * 1-5"    # daily post-market
    sentiment_refresh_cron: str = "0 8 * * 1-5"  # daily pre-market
    decision_refresh_cron: str = "30 8 * * 1-5"        # daily pre-market (after sentiment)
    fundamentals_refresh_cron: str = "0 9 * * 1-5"    # daily pre-market open
    corporate_actions_cron: str = "0 3 * * 6"         # weekly Saturday 3am (actions are infrequent)
    signal_snapshot_cron: str = "0 4 * * 6"           # weekly Saturday 4am (signal-edge trend)
    weight_tuning_cron: str = "30 4 * * 6"            # weekly Saturday 4:30am (auto-tune signal weights)
    paper_auto_trade_cron: str = "0 10 * * 1-5"       # daily after fundamentals/decision (post-open)
    india_signals_cron: str = "15 8 * * 1-5"          # daily pre-market (before decision_run at 08:30)
    regime_cron: str = "5 8 * * 1-5"                  # daily pre-market (R5, before decision_run)
    events_cron: str = "0 5 * * 6"                    # weekly Saturday 5am (R8 macro calendar refresh)
    stops_cron: str = "0 16 * * 1-5"                  # daily after US close (P3 stop-loss breach scan)
    data_quality_cron: str = "30 17 * * 1-5"          # daily post-close (P9 data-reliability scan)
    ml_train_cron: str = "0 6 * * 6"                  # weekly Saturday 6am (P14 ML retrain)

    # ML directional signal (P14)
    ml_model_dir: str = "data/models"                 # on the faiss_data volume
    ml_horizon_days: int = 5
    ml_threshold: float = 0.0                         # P(return > threshold over horizon)
    ml_max_symbols: int = 0                           # 0 = all tracked symbols with data

    # Tracked symbols — defaults to all 700+ US+India symbols from backend/data/symbols.py.
    # Override with TRACKED_SYMBOLS env var for a custom subset.
    tracked_symbols: str = Field(default_factory=_default_tracked_symbols)

    # Live stream (WebSocket dashboard)
    stream_interval_seconds: int = 5
    stream_max_symbols: int = 8

    # Paper trading
    paper_starting_cash: float = 100_000.0
    # Auto-execute paper trades from decisions each cycle (R1.1/R2.3). Off by default:
    # turning it on lets the scheduler trade the paper book unattended. Universe is the
    # watchlist ∪ current paper positions (bounded). Equity is always snapshotted regardless.
    paper_auto_trade_enabled: bool = False

    # CORS
    cors_origins: str = "*"

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.api_key in _INSECURE_API_KEYS:
            raise ValueError(
                "API_KEY is set to an insecure default. "
                "Set a strong secret in your .env file before starting."
            )
        active_llm_key = (
            self.gemini_api_key if self.llm_provider == "gemini" else self.openai_api_key
        )
        if not active_llm_key:
            raise ValueError(
                f"LLM provider is '{self.llm_provider}' but the corresponding API key is not set. "
                f"Set {'GEMINI_API_KEY' if self.llm_provider == 'gemini' else 'OPENAI_API_KEY'} in your .env file."
            )
        return self


settings = Settings()
