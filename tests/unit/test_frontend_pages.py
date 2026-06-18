"""T13: Smoke-tests for the Streamlit page render() functions and api_client.

Modules are imported the same bare way the app does (`api_client`, `page_modules.*`);
conftest puts frontend/ on sys.path so these resolve.
"""
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_st():
    """Return a MagicMock that handles st.tabs(), st.columns(), context managers."""
    st = MagicMock()
    # tabs returns a list of context-manager mocks
    tab_cm = MagicMock()
    tab_cm.__enter__ = MagicMock(return_value=tab_cm)
    tab_cm.__exit__ = MagicMock(return_value=False)
    st.tabs.return_value = [tab_cm] * 5

    # columns returns context-manager mocks sized to the requested layout:
    # st.columns(3) -> 3 cols, st.columns([1, 5]) -> 2 cols.
    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__ = MagicMock(return_value=c)
            c.__exit__ = MagicMock(return_value=False)
            c.button.return_value = False  # in-column buttons un-clicked by default
            cols.append(c)
        return cols
    st.columns.side_effect = _columns
    # expander is a context manager
    exp = MagicMock()
    exp.__enter__ = MagicMock(return_value=exp)
    exp.__exit__ = MagicMock(return_value=False)
    st.expander.return_value = exp
    # chat_message is a context manager
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    st.chat_message.return_value = cm
    # spinner is a context manager
    spin = MagicMock()
    spin.__enter__ = MagicMock(return_value=spin)
    spin.__exit__ = MagicMock(return_value=False)
    st.spinner.return_value = spin
    st.session_state = {}
    return st


# ---------------------------------------------------------------------------
# api_client
# ---------------------------------------------------------------------------

def test_api_client_get_calls_correct_url_with_headers():
    import api_client as client
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"price": 150.0}
    with patch("api_client.httpx.get", return_value=mock_resp) as mock_get:
        result = client.get("/v1/stocks/AAPL/quote")
    mock_get.assert_called_once()
    url = mock_get.call_args[0][0]
    assert url == f"{client.API_BASE}/v1/stocks/AAPL/quote"
    assert mock_get.call_args[1]["headers"] == {"X-API-Key": client.API_KEY}
    assert result == {"price": 150.0}


def test_api_client_post_sends_json_body():
    import api_client as client
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "42", "sources": []}
    with patch("api_client.httpx.post", return_value=mock_resp) as mock_post:
        result = client.post("/v1/query", {"query": "revenue?", "top_k": 5})
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["json"] == {"query": "revenue?", "top_k": 5}
    assert result == {"answer": "42", "sources": []}


# ---------------------------------------------------------------------------
# market_overview
# ---------------------------------------------------------------------------

def test_market_overview_render_calls_quote_endpoint():
    st = _mock_st()
    st.text_input.return_value = "AAPL,MSFT,GOOGL"
    # Only the "Refresh Quotes" button is clicked, not "Load Chart" (which would
    # fire a second OHLCV fetch with chart-shaped data).
    st.button.side_effect = lambda label, *a, **k: label == "Refresh Quotes"

    quote_data = {"price": 175.0, "change_pct": 1.5}

    with patch("page_modules.market_overview.st", st), \
         patch("page_modules.market_overview.get", return_value=quote_data) as mock_get:
        from page_modules.market_overview import render
        render()

    paths = [c[0][0] for c in mock_get.call_args_list]
    assert "/v1/stocks/AAPL/quote" in paths
    assert "/v1/stocks/MSFT/quote" in paths
    assert "/v1/stocks/GOOGL/quote" in paths


def test_market_overview_render_no_button_click_makes_no_api_calls():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.button.return_value = False  # not clicked

    with patch("page_modules.market_overview.st", st), \
         patch("page_modules.market_overview.get") as mock_get:
        from page_modules.market_overview import render
        render()

    mock_get.assert_not_called()


def test_market_overview_handles_api_error_gracefully():
    st = _mock_st()
    st.text_input.return_value = "BADSYM"
    st.button.return_value = True

    with patch("page_modules.market_overview.st", st), \
         patch("page_modules.market_overview.get", side_effect=Exception("404 Not Found")):
        from page_modules.market_overview import render
        render()  # must not raise


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------

def test_analytics_render_calls_analytics_endpoint():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.slider.return_value = 60
    st.button.return_value = True

    analytics_data = {
        "data": [
            {"timestamp": "2026-01-02T00:00:00", "close": 150.0,
             "sma_20": 148.0, "ema_20": 149.0, "rsi_14": 55.0}
        ]
    }

    # render() fetches analytics AND ohlcv; route each path to the right payload.
    def _get(path, **kw):
        return analytics_data if path == "/v1/analytics/AAPL" else []

    with patch("page_modules.analytics.st", st), \
         patch("page_modules.analytics.get", side_effect=_get) as mock_get:
        from page_modules.analytics import render
        render()

    mock_get.assert_any_call("/v1/analytics/AAPL", days=60)


def test_analytics_render_shows_warning_on_empty_data():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.slider.return_value = 60
    st.button.return_value = True

    with patch("page_modules.analytics.st", st), \
         patch("page_modules.analytics.get", return_value={"data": []}):
        from page_modules.analytics import render
        render()

    st.warning.assert_called_once()


def test_analytics_render_no_button_click_makes_no_api_calls():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.slider.return_value = 60
    st.button.return_value = False

    with patch("page_modules.analytics.st", st), \
         patch("page_modules.analytics.get") as mock_get:
        from page_modules.analytics import render
        render()

    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# ai_insights
# ---------------------------------------------------------------------------

def test_ai_insights_render_calls_reports_endpoint():
    st = _mock_st()
    st.button.return_value = False        # don't fire "Generate New Reports"
    st.select_slider.return_value = 10    # limit
    reports = [
        {"created_at": "2026-01-02T19:00:00", "query": "AAPL sector summary", "response": "Strong buy."},
        {"created_at": "2026-01-03T19:00:00", "query": "MSFT sector summary", "response": "Hold."},
    ]

    with patch("page_modules.ai_insights.st", st), \
         patch("page_modules.ai_insights.get", return_value=reports) as mock_get:
        from page_modules.ai_insights import render
        render()

    mock_get.assert_called_once_with("/v1/reports", limit=10)
    assert st.expander.call_count == 2


def test_ai_insights_render_shows_info_when_no_reports():
    st = _mock_st()
    st.button.return_value = False
    st.select_slider.return_value = 10

    with patch("page_modules.ai_insights.st", st), \
         patch("page_modules.ai_insights.get", return_value=[]):
        from page_modules.ai_insights import render
        render()

    st.info.assert_called_once()
    st.expander.assert_not_called()


# ---------------------------------------------------------------------------
# rag_chat
# ---------------------------------------------------------------------------

class _AttrDict(dict):
    """dict that also supports attribute access, like st.session_state."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as exc:
            raise AttributeError(k) from exc

    def __setattr__(self, k, v):
        self[k] = v


def _rag_st_with_history(history=None):
    """session_state must support attribute access (st.session_state.chat_history)
    and real dict semantics (st.session_state.pop(...))."""
    st = _mock_st()
    st.button.return_value = False  # don't fire "Clear Chat"
    state = _AttrDict()
    state["chat_history"] = history if history is not None else []
    st.session_state = state
    return st


def test_rag_chat_render_posts_query_and_displays_answer():
    st = _rag_st_with_history([])
    st.chat_input.return_value = "What is revenue trend?"
    rag_result = {"answer": "Revenue grew 12% YoY.", "sources": [{"doc_id": "d1", "chunk_id": 0, "score": 0.91}]}

    with patch("page_modules.rag_chat.st", st), \
         patch("page_modules.rag_chat.post", return_value=rag_result) as mock_post:
        import page_modules.rag_chat as rag_mod
        rag_mod.render()

    mock_post.assert_called_once_with("/v1/query", {"query": "What is revenue trend?", "top_k": 5})


def test_rag_chat_render_no_input_makes_no_api_calls():
    st = _rag_st_with_history([])
    st.chat_input.return_value = None  # no input

    with patch("page_modules.rag_chat.st", st), \
         patch("page_modules.rag_chat.post") as mock_post:
        import page_modules.rag_chat as rag_mod
        rag_mod.render()

    mock_post.assert_not_called()


def test_rag_chat_appends_to_session_history():
    history = []
    st = _rag_st_with_history(history)
    st.chat_input.return_value = "Tell me about AAPL."
    rag_result = {"answer": "AAPL is a tech giant.", "sources": []}

    with patch("page_modules.rag_chat.st", st), \
         patch("page_modules.rag_chat.post", return_value=rag_result):
        import page_modules.rag_chat as rag_mod
        rag_mod.render()

    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Tell me about AAPL."}
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "AAPL is a tech giant."


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def _job_row(**over):
    row = {"id": "abc-12345", "type": "market_refresh", "status": "completed",
           "started_at": "2026-01-02T08:00:00", "finished_at": "2026-01-02T08:01:00",
           "error": None}
    row.update(over)
    return row


def test_jobs_render_lists_recent_jobs():
    st = _mock_st()
    st.button.return_value = False      # no triggers / refresh / lookup
    st.text_input.return_value = ""
    jobs = [_job_row(), _job_row(type="decision_run", status="failed", error="boom")]

    with patch("page_modules.jobs.st", st), \
         patch("page_modules.jobs.get", return_value=jobs) as mock_get:
        from page_modules.jobs import render
        render()

    mock_get.assert_called_once_with("/v1/jobs", limit=30)


def test_jobs_lookup_by_id_calls_endpoint():
    st = _mock_st()
    st.button.side_effect = lambda label, *a, **k: label == "Lookup"
    st.text_input.return_value = "abc-12345"
    single = {"id": "abc-12345", "type": "market_refresh", "status": "completed"}

    def _get(path, **kw):
        return single if path == "/v1/jobs/abc-12345" else [_job_row()]

    with patch("page_modules.jobs.st", st), \
         patch("page_modules.jobs.get", side_effect=_get) as mock_get:
        from page_modules.jobs import render
        render()

    mock_get.assert_any_call("/v1/jobs/abc-12345")
    st.json.assert_called_once_with(single)


def test_jobs_render_no_lookup_when_id_blank():
    st = _mock_st()
    st.button.side_effect = lambda label, *a, **k: label == "Lookup"
    st.text_input.return_value = "   "  # blank after strip → lookup guarded
    calls = []

    def _get(path, **kw):
        calls.append(path)
        return [_job_row()]

    with patch("page_modules.jobs.st", st), \
         patch("page_modules.jobs.get", side_effect=_get):
        from page_modules.jobs import render
        render()

    assert calls == ["/v1/jobs"]  # only the recent-jobs table, no lookup fetch
    st.json.assert_not_called()


def test_jobs_render_shows_error_on_table_fetch():
    st = _mock_st()
    st.button.return_value = False
    st.text_input.return_value = ""

    with patch("page_modules.jobs.st", st), \
         patch("page_modules.jobs.get", side_effect=Exception("boom")):
        from page_modules.jobs import render
        render()  # must not raise

    st.error.assert_called_once()


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------

def test_watchlist_render_lists_positions():
    st = _mock_st()
    st.button.return_value = False  # don't trigger Save / row-delete
    data = {
        "items": [{
            "symbol": "AAPL", "quantity": 10.0, "cost_basis": 100.0, "note": "core",
            "current_price": 150.0, "market_value": 1500.0,
            "unrealized_pnl": 500.0, "unrealized_pnl_pct": 0.5,
            "recommendation": "BUY", "confidence": 0.8, "risk_level": "Low",
            "sentiment_score": 0.42,
        }],
        "totals": {"positions": 1, "market_value": 1500.0, "cost_value": 1000.0,
                   "unrealized_pnl": 500.0, "unrealized_pnl_pct": 0.5},
    }

    with patch("page_modules.watchlist.st", st), \
         patch("page_modules.watchlist.get", return_value=data) as mock_get:
        from page_modules.watchlist import render
        render()

    mock_get.assert_called_once_with("/v1/watchlist")


def test_watchlist_render_empty_shows_info():
    st = _mock_st()
    st.button.return_value = False

    with patch("page_modules.watchlist.st", st), \
         patch("page_modules.watchlist.get", return_value={"items": [], "totals": {}}):
        from page_modules.watchlist import render
        render()

    st.info.assert_called_once()


# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------

def test_performance_render_no_click_makes_no_api_calls():
    st = _mock_st()
    st.button.return_value = False

    with patch("page_modules.performance.st", st), \
         patch("page_modules.performance.get") as mock_get:
        from page_modules.performance import render
        render()

    mock_get.assert_not_called()
    st.info.assert_called_once()


def test_performance_render_shows_results():
    st = _mock_st()
    st.button.return_value = True
    st.text_input.return_value = ""  # all symbols
    data = {
        "overall": {"count": 3, "hit_rate": 0.67, "avg_return": 0.04},
        "by_recommendation": {"BUY": {"count": 2, "hit_rate": 0.5, "avg_return": 0.02}},
        "by_risk_level": {"Low": {"count": 3, "hit_rate": 0.67, "avg_return": 0.04}},
        "cumulative_return": 0.12,
        "pending_count": 1,
        "recent": [{
            "symbol": "AAPL", "decision_date": "2026-01-01", "recommendation": "BUY",
            "entry_price": 100.0, "exit_price": 110.0, "realized_move": 0.1,
            "strategy_return": 0.1, "correct": True,
        }],
    }

    with patch("page_modules.performance.st", st), \
         patch("page_modules.performance.get", return_value=data) as mock_get:
        from page_modules.performance import render
        render()

    assert mock_get.call_args_list[0][0][0] == "/v1/performance"


def test_performance_render_warns_when_no_evaluable():
    st = _mock_st()
    st.button.return_value = True
    st.text_input.return_value = ""

    with patch("page_modules.performance.st", st), \
         patch("page_modules.performance.get", return_value={"overall": {"count": 0}, "pending_count": 4}):
        from page_modules.performance import render
        render()

    st.warning.assert_called_once()


# ---------------------------------------------------------------------------
# paper trading
# ---------------------------------------------------------------------------

def test_paper_render_shows_summary():
    st = _mock_st()
    st.button.return_value = False  # no trade / reset
    summary = {
        "metrics": {"equity": 100_400.0, "total_return": 0.004, "cash": 98_450.0,
                    "positions_value": 1950.0, "unrealized_pnl": 300.0, "starting_cash": 100_000.0},
        "positions": [{"symbol": "AAPL", "quantity": 15, "avg_cost": 110.0,
                       "current_price": 130.0, "market_value": 1950.0, "unrealized_pnl": 300.0}],
    }

    def _get(path, **kw):
        return summary if path == "/v1/paper" else {"trades": []}

    with patch("page_modules.paper.st", st), \
         patch("page_modules.paper.get", side_effect=_get) as mock_get:
        from page_modules.paper import render
        render()

    assert mock_get.call_args_list[0][0][0] == "/v1/paper"


def test_paper_render_empty_positions_shows_info():
    st = _mock_st()
    st.button.return_value = False

    def _get(path, **kw):
        return {"metrics": {}, "positions": []} if path == "/v1/paper" else {"trades": []}

    with patch("page_modules.paper.st", st), \
         patch("page_modules.paper.get", side_effect=_get):
        from page_modules.paper import render
        render()

    st.info.assert_called()


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------

def test_calibration_render_no_click_makes_no_api_calls():
    st = _mock_st()
    st.button.return_value = False

    with patch("page_modules.calibration.st", st), \
         patch("page_modules.calibration.get") as mock_get:
        from page_modules.calibration import render
        render()

    mock_get.assert_not_called()
    st.info.assert_called_once()


def test_calibration_render_shows_results():
    st = _mock_st()
    st.button.return_value = True
    st.text_input.return_value = ""
    data = {
        "reliability": {
            "count": 4, "ece": 0.1, "brier_score": 0.01,
            "bins": [{"bin_lower": 0.9, "bin_upper": 1.0, "count": 2,
                      "mean_confidence": 0.9, "hit_rate": 1.0, "gap": 0.1}],
        },
        "signals": [{"signal": "rsi", "active_count": 2, "accuracy": 1.0,
                     "avg_abs_score": 1.0, "avg_weight": 0.12}],
        "threshold_tuning": {
            "current": {"threshold": 0.3, "trades": 3, "hit_rate": 0.66, "avg_return": 0.01, "coverage": 0.5},
            "current_threshold": 0.3,
            "grid": [{"threshold": 0.1, "trades": 5, "hit_rate": 0.8, "avg_return": 0.02, "coverage": 1.0},
                     {"threshold": 0.6, "trades": 0, "hit_rate": None, "avg_return": 0.0, "coverage": 0.0}],
            "best": {"threshold": 0.1, "trades": 5, "hit_rate": 0.8, "avg_return": 0.02, "coverage": 1.0},
        },
    }

    with patch("page_modules.calibration.st", st), \
         patch("page_modules.calibration.get", return_value=data) as mock_get:
        from page_modules.calibration import render
        render()

    # first fetch is the calibration payload (a later one fetches /history)
    assert mock_get.call_args_list[0][0][0] == "/v1/calibration"


def test_calibration_render_warns_when_no_data():
    st = _mock_st()
    st.button.return_value = True
    st.text_input.return_value = ""

    with patch("page_modules.calibration.st", st), \
         patch("page_modules.calibration.get", return_value={"reliability": {"count": 0}}):
        from page_modules.calibration import render
        render()

    st.warning.assert_called_once()


# ---------------------------------------------------------------------------
# live (WebSocket dashboard)
# ---------------------------------------------------------------------------

def test_live_ws_url_scheme_swap():
    from page_modules.live import _ws_url
    assert _ws_url("http://localhost:8000") == "ws://localhost:8000/v1/stream"
    assert _ws_url("https://api.example.com/") == "wss://api.example.com/v1/stream"


def test_live_build_widget_html_embeds_config():
    from page_modules.live import _build_widget_html
    html = _build_widget_html("ws://x:8000/v1/stream", "secret-key", ["AAPL", "MSFT"])
    assert "ws://x:8000/v1/stream" in html
    assert "AAPL" in html and "MSFT" in html
    assert "WebSocket" in html


def test_live_render_embeds_widget():
    st = _mock_st()
    st.text_input.return_value = "AAPL,MSFT"
    comp = MagicMock()

    with patch("page_modules.live.st", st), \
         patch("page_modules.live.components", comp):
        from page_modules.live import render
        render()

    comp.html.assert_called_once()
    html = comp.html.call_args[0][0]
    assert "WebSocket" in html and "AAPL" in html


# ---------------------------------------------------------------------------
# app.py — tab wiring (static structure check)
# ---------------------------------------------------------------------------

def test_app_wires_all_tabs():
    """TABS dict contains all expected tab names with callable render functions."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("api_client.httpx.get", return_value=mock_resp), \
         patch("api_client.httpx.post", return_value=mock_resp):
        import app as app_mod
    assert set(app_mod.TABS.keys()) == {
        "Market Overview", "Live", "Watchlist", "Paper Trading", "Analytics", "Fundamentals",
        "AI Insights", "Decision Intelligence", "Performance", "Calibration", "Options Chain",
        "Portfolio", "RAG Chat", "Knowledge Base", "Jobs",
    }
    for name, fn in app_mod.TABS.items():
        assert callable(fn), f"{name} render is not callable"


def test_app_tab_render_functions_are_correct_page_renders():
    """Each TABS entry points to the render function of its corresponding page module."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("api_client.httpx.get", return_value=mock_resp), \
         patch("api_client.httpx.post", return_value=mock_resp):
        import app as app_mod
        from page_modules import market_overview, analytics, ai_insights, rag_chat, jobs

    assert app_mod.TABS["Market Overview"] is market_overview.render
    assert app_mod.TABS["Analytics"] is analytics.render
    assert app_mod.TABS["AI Insights"] is ai_insights.render
    assert app_mod.TABS["RAG Chat"] is rag_chat.render
    assert app_mod.TABS["Jobs"] is jobs.render
