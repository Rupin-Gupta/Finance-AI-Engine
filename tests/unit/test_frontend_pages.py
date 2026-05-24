"""T13: Smoke-tests for all 5 Streamlit page render() functions and api_client."""
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
    # columns returns a list of metric mocks
    col = MagicMock()
    col.__enter__ = MagicMock(return_value=col)
    col.__exit__ = MagicMock(return_value=False)
    st.columns.return_value = [col, col, col]
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
    import frontend.api_client as client
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"price": 150.0}
    with patch("frontend.api_client.httpx.get", return_value=mock_resp) as mock_get:
        result = client.get("/v1/stocks/AAPL/quote")
    mock_get.assert_called_once()
    url = mock_get.call_args[0][0]
    assert url == "http://localhost:8000/v1/stocks/AAPL/quote"
    assert mock_get.call_args[1]["headers"] == {"X-API-Key": client.API_KEY}
    assert result == {"price": 150.0}


def test_api_client_post_sends_json_body():
    import frontend.api_client as client
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "42", "sources": []}
    with patch("frontend.api_client.httpx.post", return_value=mock_resp) as mock_post:
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
    st.button.return_value = True  # simulate button click

    quote_data = {"price": 175.0, "change_pct": 1.5}

    with patch("frontend.pages.market_overview.st", st), \
         patch("frontend.pages.market_overview.get", return_value=quote_data) as mock_get:
        from frontend.pages.market_overview import render
        render()

    paths = [c[0][0] for c in mock_get.call_args_list]
    assert "/v1/stocks/AAPL/quote" in paths
    assert "/v1/stocks/MSFT/quote" in paths
    assert "/v1/stocks/GOOGL/quote" in paths


def test_market_overview_render_no_button_click_makes_no_api_calls():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.button.return_value = False  # not clicked

    with patch("frontend.pages.market_overview.st", st), \
         patch("frontend.pages.market_overview.get") as mock_get:
        from frontend.pages.market_overview import render
        render()

    mock_get.assert_not_called()


def test_market_overview_handles_api_error_gracefully():
    st = _mock_st()
    st.text_input.return_value = "BADSYM"
    st.button.return_value = True

    with patch("frontend.pages.market_overview.st", st), \
         patch("frontend.pages.market_overview.get", side_effect=Exception("404 Not Found")):
        from frontend.pages.market_overview import render
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

    with patch("frontend.pages.analytics.st", st), \
         patch("frontend.pages.analytics.get", return_value=analytics_data) as mock_get:
        from frontend.pages.analytics import render
        render()

    mock_get.assert_called_once_with("/v1/analytics/AAPL", days=60)


def test_analytics_render_shows_warning_on_empty_data():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.slider.return_value = 60
    st.button.return_value = True

    with patch("frontend.pages.analytics.st", st), \
         patch("frontend.pages.analytics.get", return_value={"data": []}):
        from frontend.pages.analytics import render
        render()

    st.warning.assert_called_once()


def test_analytics_render_no_button_click_makes_no_api_calls():
    st = _mock_st()
    st.text_input.return_value = "AAPL"
    st.slider.return_value = 60
    st.button.return_value = False

    with patch("frontend.pages.analytics.st", st), \
         patch("frontend.pages.analytics.get") as mock_get:
        from frontend.pages.analytics import render
        render()

    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# ai_insights
# ---------------------------------------------------------------------------

def test_ai_insights_render_calls_reports_endpoint():
    st = _mock_st()
    reports = [
        {"created_at": "2026-01-02T19:00:00", "query": "AAPL sector summary", "response": "Strong buy."},
        {"created_at": "2026-01-03T19:00:00", "query": "MSFT sector summary", "response": "Hold."},
    ]

    with patch("frontend.pages.ai_insights.st", st), \
         patch("frontend.pages.ai_insights.get", return_value=reports) as mock_get:
        from frontend.pages.ai_insights import render
        render()

    mock_get.assert_called_once_with("/v1/reports", limit=10)
    assert st.expander.call_count == 2


def test_ai_insights_render_shows_info_when_no_reports():
    st = _mock_st()

    with patch("frontend.pages.ai_insights.st", st), \
         patch("frontend.pages.ai_insights.get", return_value=[]):
        from frontend.pages.ai_insights import render
        render()

    st.info.assert_called_once()
    st.expander.assert_not_called()


# ---------------------------------------------------------------------------
# rag_chat
# ---------------------------------------------------------------------------

def _rag_st_with_history(history=None):
    """session_state must support attribute access (st.session_state.chat_history)."""
    st = _mock_st()
    state = MagicMock()
    state.chat_history = history if history is not None else []
    st.session_state = state
    return st


def test_rag_chat_render_posts_query_and_displays_answer():
    st = _rag_st_with_history([])
    st.chat_input.return_value = "What is revenue trend?"
    rag_result = {"answer": "Revenue grew 12% YoY.", "sources": [{"doc_id": "d1", "chunk_id": 0, "score": 0.91}]}

    with patch("frontend.pages.rag_chat.st", st), \
         patch("frontend.pages.rag_chat.post", return_value=rag_result) as mock_post:
        import frontend.pages.rag_chat as rag_mod
        rag_mod.render()

    mock_post.assert_called_once_with("/v1/query", {"query": "What is revenue trend?", "top_k": 5})


def test_rag_chat_render_no_input_makes_no_api_calls():
    st = _rag_st_with_history([])
    st.chat_input.return_value = None  # no input

    with patch("frontend.pages.rag_chat.st", st), \
         patch("frontend.pages.rag_chat.post") as mock_post:
        import frontend.pages.rag_chat as rag_mod
        rag_mod.render()

    mock_post.assert_not_called()


def test_rag_chat_appends_to_session_history():
    history = []
    st = _rag_st_with_history(history)
    st.chat_input.return_value = "Tell me about AAPL."
    rag_result = {"answer": "AAPL is a tech giant.", "sources": []}

    with patch("frontend.pages.rag_chat.st", st), \
         patch("frontend.pages.rag_chat.post", return_value=rag_result):
        import frontend.pages.rag_chat as rag_mod
        rag_mod.render()

    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Tell me about AAPL."}
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "AAPL is a tech giant."


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def test_jobs_render_calls_jobs_endpoint():
    st = _mock_st()
    st.text_input.return_value = "abc-123"
    st.button.return_value = True
    job_data = {"id": "abc-123", "type": "market_ingest", "status": "completed"}

    with patch("frontend.pages.jobs.st", st), \
         patch("frontend.pages.jobs.get", return_value=job_data) as mock_get:
        from frontend.pages.jobs import render
        render()

    mock_get.assert_called_once_with("/v1/jobs/abc-123")
    st.json.assert_called_once_with(job_data)


def test_jobs_render_no_job_id_makes_no_api_calls():
    st = _mock_st()
    st.text_input.return_value = ""
    st.button.return_value = True

    with patch("frontend.pages.jobs.st", st), \
         patch("frontend.pages.jobs.get") as mock_get:
        from frontend.pages.jobs import render
        render()

    mock_get.assert_not_called()


def test_jobs_render_shows_error_on_not_found():
    st = _mock_st()
    st.text_input.return_value = "bad-id"
    st.button.return_value = True

    with patch("frontend.pages.jobs.st", st), \
         patch("frontend.pages.jobs.get", side_effect=Exception("404")):
        from frontend.pages.jobs import render
        render()  # must not raise

    st.error.assert_called_once()


# ---------------------------------------------------------------------------
# app.py — tab wiring (static structure check)
# ---------------------------------------------------------------------------

def test_app_wires_all_five_tabs():
    """TABS dict contains all 5 expected tab names with callable render functions."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("frontend.api_client.httpx.get", return_value=mock_resp), \
         patch("frontend.api_client.httpx.post", return_value=mock_resp):
        import frontend.app as app_mod
    assert set(app_mod.TABS.keys()) == {
        "Market Overview", "Analytics", "AI Insights", "RAG Chat", "Jobs"
    }
    for name, fn in app_mod.TABS.items():
        assert callable(fn), f"{name} render is not callable"


def test_app_tab_render_functions_are_correct_page_renders():
    """Each TABS entry points to the render function of its corresponding page module."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("frontend.api_client.httpx.get", return_value=mock_resp), \
         patch("frontend.api_client.httpx.post", return_value=mock_resp):
        import frontend.app as app_mod
        from frontend.pages import market_overview, analytics, ai_insights, rag_chat, jobs

    assert app_mod.TABS["Market Overview"] is market_overview.render
    assert app_mod.TABS["Analytics"] is analytics.render
    assert app_mod.TABS["AI Insights"] is ai_insights.render
    assert app_mod.TABS["RAG Chat"] is rag_chat.render
    assert app_mod.TABS["Jobs"] is jobs.render
