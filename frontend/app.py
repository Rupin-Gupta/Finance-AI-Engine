import streamlit as st

st.set_page_config(
    page_title="Finance AI Console",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from page_modules import (
    market_overview, analytics, ai_insights, rag_chat, jobs, data_upload,
    decision_intelligence, fundamentals, options, portfolio, watchlist,
    performance, live, calibration, paper,
)
import _theme
from api_client import get

# Name → render fn. (Kept as a flat dict — the app's stable contract.)
TABS = {
    "Market Overview": market_overview.render,
    "Live": live.render,
    "Watchlist": watchlist.render,
    "Paper Trading": paper.render,
    "Analytics": analytics.render,
    "Fundamentals": fundamentals.render,
    "AI Insights": ai_insights.render,
    "Decision Intelligence": decision_intelligence.render,
    "Performance": performance.render,
    "Calibration": calibration.render,
    "Options Chain": options.render,
    "Portfolio": portfolio.render,
    "RAG Chat": rag_chat.render,
    "Knowledge Base": data_upload.render,
    "Jobs": jobs.render,
}

# Grouped navigation — only the selected page renders (fast; no firing all 15 at once).
SECTIONS = {
    "📊  Markets": ["Market Overview", "Live", "Analytics", "Fundamentals", "Options Chain"],
    "🎯  Decisions": ["Decision Intelligence", "AI Insights"],
    "💼  Portfolio": ["Watchlist", "Paper Trading", "Portfolio"],
    "📈  Learning": ["Performance", "Calibration"],
    "💬  Knowledge": ["RAG Chat", "Knowledge Base"],
    "⚙️  System": ["Jobs"],
}

ICONS = {
    "Market Overview": "📈", "Live": "🟢", "Watchlist": "⭐", "Paper Trading": "🧪",
    "Analytics": "📊", "Fundamentals": "🏦", "AI Insights": "🧠",
    "Decision Intelligence": "🎯", "Performance": "✅", "Calibration": "🎚️",
    "Options Chain": "⛓️", "Portfolio": "💼", "RAG Chat": "💬",
    "Knowledge Base": "📚", "Jobs": "⚙️",
}


@st.cache_data(ttl=60, show_spinner=False)
def _status() -> tuple[dict | None, bool | None]:
    """Live regime + API health for the top bar (cached 60s)."""
    regime, ready = None, None
    try:
        get("/health")
        ready = True
        regime = get("/v1/regime")
    except Exception:
        if ready is None:
            ready = False
    return regime, ready


def main() -> None:
    _theme.inject()

    with st.sidebar:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:.5rem;padding:.2rem 0 1rem'>"
            "<span style='display:grid;place-items:center;width:30px;height:30px;border-radius:8px;"
            "background:#F5B301;color:#0B0E13;font-weight:800;font-family:Space Grotesk'>F</span>"
            "<span style='font-family:Space Grotesk;font-weight:700'>Finance<span style='color:#F5B301'>AI</span></span>"
            "</div>",
            unsafe_allow_html=True,
        )
        section = st.radio("Section", list(SECTIONS.keys()), key="nav_section", label_visibility="collapsed")
        st.caption(section.split("  ")[-1].upper())
        page = st.radio(
            "Page",
            SECTIONS[section],
            format_func=lambda n: f"{ICONS.get(n, '•')}  {n}",
            key=f"nav_page_{section}",
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("Same engine as the API · /v1/*")

    regime, ready = _status()
    _theme.topbar(f"{ICONS.get(page, '')}  {page}", regime, ready)
    TABS[page]()


main()
