import os
import sys
from pathlib import Path

# The Streamlit frontend runs with frontend/ as the working dir, so its modules
# use bare imports (`from api_client import get`, `from page_modules import ...`).
# Put frontend/ on sys.path so tests can import them the same way the app does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

# Set before any backend module is imported so Settings() validator passes.
os.environ.setdefault("API_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key-for-tests")
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/finance")
os.environ.setdefault("FINNHUB_API_KEY", "fake-finnhub-key")

TEST_API_KEY = os.environ["API_KEY"]
