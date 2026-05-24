import pytest
from backend.reporting import sector_report as sr_mod


def _make_analytics_rows(rows):
    return [dict(r) for r in rows]


class FakeConn:
    def __init__(self, analytics_rows, chat_id="chat-1"):
        self._analytics_rows = analytics_rows
        self._chat_id = chat_id
        self.chat_written = []

    async def fetch(self, query, *args):
        # _latest_analytics_per_symbol
        return self._analytics_rows

    async def fetchrow(self, query, *args):
        if "INSERT INTO chat_history" in query:
            self.chat_written.append(args)
            return {"id": self._chat_id}
        raise AssertionError(f"unexpected fetchrow: {query!r}")


def _row(symbol, sector=None, sma=101.0, ema=100.5, rsi=55.0, vol=0.2, mom=0.01):
    return {
        "symbol": symbol, "sector": sector,
        "sma_20": sma, "ema_20": ema, "rsi_14": rsi,
        "volatility_20": vol, "momentum_10": mom,
        "timestamp": "2026-05-14",
    }


# --- happy path ---

@pytest.mark.asyncio
async def test_run_sector_report_calls_llm_per_symbol(monkeypatch):
    rows = [_row("AAPL", "Technology"), _row("MSFT", "Technology"), _row("JPM", "Finance")]
    conn = FakeConn(rows)

    prompts_seen = []

    class FakeLLM:
        async def complete(self, prompt):
            prompts_seen.append(prompt)
            return f"Report for prompt #{len(prompts_seen)}"

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    chat_ids = await sr_mod.run_sector_report(conn)

    assert len(prompts_seen) == 3
    assert len(chat_ids) == 3
    assert len(conn.chat_written) == 3


@pytest.mark.asyncio
async def test_run_sector_report_prompt_contains_symbol_and_metrics(monkeypatch):
    rows = [_row("AAPL", "Technology", sma=150.5, rsi=62.3)]
    conn = FakeConn(rows)

    prompts_seen = []

    class FakeLLM:
        async def complete(self, prompt):
            prompts_seen.append(prompt)
            return "Summary text."

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    await sr_mod.run_sector_report(conn)

    assert len(prompts_seen) == 1
    prompt = prompts_seen[0]
    assert "AAPL" in prompt
    assert "Technology" in prompt
    assert "150.5" in prompt or "150" in prompt
    assert "62.3" in prompt or "62" in prompt


@pytest.mark.asyncio
async def test_run_sector_report_writes_chat_history_v12(monkeypatch):
    rows = [_row("TSLA", "Automotive")]
    conn = FakeConn(rows, chat_id="chat-xyz")

    class FakeLLM:
        async def complete(self, prompt):
            return "Tesla looking strong."

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    chat_ids = await sr_mod.run_sector_report(conn)

    # V12: report stored in chat_history
    assert chat_ids == ["chat-xyz"]
    assert len(conn.chat_written) == 1
    # fetchrow args: (user_id, query, response, sources_json)
    _user_id, query_arg, response_arg, _sources = conn.chat_written[0]
    assert "TSLA" in query_arg
    assert response_arg == "Tesla looking strong."


@pytest.mark.asyncio
async def test_run_sector_report_null_sector_grouped_as_unknown(monkeypatch):
    rows = [_row("NVDA", sector=None)]
    conn = FakeConn(rows)

    prompts_seen = []

    class FakeLLM:
        async def complete(self, prompt):
            prompts_seen.append(prompt)
            return "Report."

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    await sr_mod.run_sector_report(conn)

    assert "Unknown" in prompts_seen[0]


@pytest.mark.asyncio
async def test_run_sector_report_null_metrics_rendered_as_na(monkeypatch):
    rows = [_row("AMZN", "Consumer", sma=None, rsi=None)]
    conn = FakeConn(rows)

    prompts_seen = []

    class FakeLLM:
        async def complete(self, prompt):
            prompts_seen.append(prompt)
            return "Report."

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    await sr_mod.run_sector_report(conn)

    assert "N/A" in prompts_seen[0]


# --- empty analytics table ---

@pytest.mark.asyncio
async def test_run_sector_report_no_rows_returns_empty(monkeypatch):
    conn = FakeConn([])

    llm_called = []

    class FakeLLM:
        async def complete(self, prompt):
            llm_called.append(prompt)
            return "x"

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: FakeLLM())

    chat_ids = await sr_mod.run_sector_report(conn)

    assert chat_ids == []
    assert llm_called == []


# --- LLM error propagates ---

@pytest.mark.asyncio
async def test_run_sector_report_llm_error_propagates(monkeypatch):
    rows = [_row("GOOGL", "Technology")]
    conn = FakeConn(rows)

    class BrokenLLM:
        async def complete(self, prompt):
            raise ConnectionError("quota exceeded")

    monkeypatch.setattr(sr_mod, "get_llm_client", lambda: BrokenLLM())

    with pytest.raises(ConnectionError, match="quota exceeded"):
        await sr_mod.run_sector_report(conn)
