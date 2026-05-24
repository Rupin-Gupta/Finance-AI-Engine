import os

# Set before any backend module is imported so Settings() validator passes.
os.environ.setdefault("API_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key-for-tests")
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/finance")
os.environ.setdefault("FINNHUB_API_KEY", "fake-finnhub-key")

TEST_API_KEY = os.environ["API_KEY"]
