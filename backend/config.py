from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    decision_refresh_cron: str = "30 8 * * 1-5"  # daily pre-market (after sentiment)

    # Tracked symbols
    tracked_symbols: str = "AAPL,MSFT,GOOGL,AMZN,TSLA"

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
