"""Live stream: connection manager, tick payload, alerts-since query."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.api.stream import ConnectionManager, build_tick_payload
from backend.db.queries import alerts as alerts_q


class FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, msg):
        if self.fail:
            raise RuntimeError("client gone")
        self.sent.append(msg)


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_register_and_count():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect(ws)
    assert ws.accepted is True
    assert mgr.count == 1


@pytest.mark.asyncio
async def test_set_symbols_and_subscribed_union():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect(a)
    await mgr.connect(b)
    await mgr.set_symbols(a, ["AAPL", "MSFT"])
    await mgr.set_symbols(b, ["MSFT", "TSLA"])
    assert mgr.subscribed_union() == {"AAPL", "MSFT", "TSLA"}


@pytest.mark.asyncio
async def test_disconnect_removes_client():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect(ws)
    mgr.disconnect(ws)
    assert mgr.count == 0


@pytest.mark.asyncio
async def test_broadcast_sends_and_prunes_dead_clients():
    mgr = ConnectionManager()
    good, bad = FakeWS(), FakeWS(fail=True)
    await mgr.connect(good)
    await mgr.connect(bad)

    dropped = await mgr.broadcast({"type": "tick"})

    assert dropped == 1
    assert good.sent == [{"type": "tick"}]
    assert mgr.count == 1          # dead client pruned
    assert bad not in mgr._clients


# ---------------------------------------------------------------------------
# build_tick_payload
# ---------------------------------------------------------------------------

def test_build_tick_payload_shape():
    quotes = {"AAPL": {"price": 150.0, "change_pct": 1.2, "source": "finnhub"}}
    decisions = {"AAPL": {"recommendation": "BUY", "confidence": 0.8, "risk_level": "Low"}}
    alerts = [{"symbol": "AAPL", "alert_type": "zscore_spike", "value": 3.4, "threshold": 3.0}]

    payload = build_tick_payload(quotes, decisions, alerts)

    assert payload["type"] == "tick"
    assert payload["quotes"] == quotes
    assert payload["decisions"] == decisions
    assert payload["alerts"] == alerts
    assert "ts" in payload


# ---------------------------------------------------------------------------
# get_alerts_since
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_alerts_since_passes_timestamp_and_returns_rows():
    rows = [{"id": "a1", "symbol": "AAPL", "alert_type": "spike",
             "value": 3.4, "threshold": 3.0, "detected_at": datetime.now(tz=timezone.utc)}]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = await alerts_q.get_alerts_since(conn, since)

    assert out == rows
    assert conn.fetch.call_args[0][1] == since
