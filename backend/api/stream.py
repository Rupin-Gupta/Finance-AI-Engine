"""Real-time streaming: WebSocket connection manager + background broadcaster.

The broadcaster runs as a single background task (started in main.py lifespan) and
pushes live quotes + latest decisions + new alerts to all connected clients every
few seconds. Clients subscribe to a symbol set; the broadcaster fetches the union.
"""
import asyncio
import logging
from datetime import datetime, timezone

from backend.config import settings
from backend.ingest.market import fetch_finnhub_quote
from backend.db.queries.market_data import get_latest_prices
from backend.db.queries.decisions import get_latest_decisions_multi
from backend.db.queries.alerts import get_alerts_since

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks active WebSocket clients and the symbols each is subscribed to."""

    def __init__(self) -> None:
        self._clients: dict = {}  # ws -> set[str]
        self._lock = asyncio.Lock()

    async def connect(self, ws) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[ws] = set()

    def disconnect(self, ws) -> None:
        self._clients.pop(ws, None)

    async def set_symbols(self, ws, symbols) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients[ws] = set(symbols)

    def subscribed_union(self) -> set:
        union: set = set()
        for syms in self._clients.values():
            union |= syms
        return union

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict) -> int:
        """Send `message` to every client; drop any that raise. Returns #dropped."""
        dead = []
        for ws in list(self._clients.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        return len(dead)


manager = ConnectionManager()


def build_tick_payload(quotes: dict, decisions: dict, alerts: list) -> dict:
    """Assemble one broadcast frame. Pure — no I/O."""
    return {
        "type": "tick",
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "quotes": quotes,
        "decisions": decisions,
        "alerts": alerts,
    }


def _fallback_symbols(max_symbols: int) -> list[str]:
    syms = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    return syms[:max_symbols]


async def _collect_tick(pool, symbols: list[str], since: datetime) -> tuple[dict, dict, list, datetime]:
    """Gather quotes/decisions/new-alerts for `symbols`. Returns (quotes, decisions, alerts, new_since)."""
    quote_results = await asyncio.gather(
        *[fetch_finnhub_quote(s) for s in symbols], return_exceptions=True
    )
    quotes: dict = {}
    missing: list[str] = []
    for s, q in zip(symbols, quote_results):
        if isinstance(q, dict) and q:
            quotes[s] = {"price": q["price"], "change_pct": q.get("change_pct"), "source": "finnhub"}
        else:
            missing.append(s)

    async with pool.acquire() as conn:
        if missing:
            for s, price in (await get_latest_prices(conn, missing)).items():
                quotes[s] = {"price": price, "change_pct": None, "source": "db"}
        dec_rows = await get_latest_decisions_multi(conn, symbols)
        new_alerts = await get_alerts_since(conn, since)

    decisions = {
        s: {
            "recommendation": r["recommendation"],
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "risk_level": r["risk_level"],
        }
        for s, r in dec_rows.items()
    }
    alerts = [
        {
            "symbol": a["symbol"],
            "alert_type": a["alert_type"],
            "value": float(a["value"]) if a["value"] is not None else None,
            "threshold": float(a["threshold"]) if a["threshold"] is not None else None,
            "detected_at": a["detected_at"].isoformat() if a["detected_at"] else None,
        }
        for a in new_alerts
    ]
    new_since = max((a["detected_at"] for a in new_alerts), default=since)
    return quotes, decisions, alerts, new_since


async def run_broadcaster(manager: ConnectionManager, pool, interval: int, max_symbols: int) -> None:
    """Background loop: every `interval` seconds, broadcast a tick to all clients."""
    since = datetime.now(tz=timezone.utc)
    logger.info("stream broadcaster started (interval=%ds, max_symbols=%d)", interval, max_symbols)
    while True:
        try:
            await asyncio.sleep(interval)
            if manager.count == 0:
                continue
            symbols = sorted(manager.subscribed_union()) or _fallback_symbols(max_symbols)
            symbols = symbols[:max_symbols]
            if not symbols:
                continue
            quotes, decisions, alerts, since = await _collect_tick(pool, symbols, since)
            await manager.broadcast(build_tick_payload(quotes, decisions, alerts))
        except asyncio.CancelledError:
            logger.info("stream broadcaster stopped")
            raise
        except Exception as exc:
            logger.warning("stream broadcaster tick failed: %s", exc)
