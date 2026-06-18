"""WebSocket endpoint for the live dashboard.

Auth is via the `api_key` query param because browsers cannot set custom headers
(e.g. X-API-Key) on a WebSocket handshake. Same key/comparison as backend/api/auth.py.
"""
import hmac
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.api.stream import manager
from backend.api.validators import validate_symbol

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    key = ws.query_params.get("api_key", "")
    if not key or not hmac.compare_digest(key, settings.api_key):
        await ws.close(code=1008)  # policy violation
        return

    await manager.connect(ws)
    try:
        await ws.send_json({"type": "connected"})
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
                symbols = []
                for raw in (msg.get("symbols") or [])[: settings.stream_max_symbols]:
                    try:
                        symbols.append(validate_symbol(str(raw)))
                    except Exception:
                        continue  # skip invalid tickers
                await manager.set_symbols(ws, symbols)
                await ws.send_json({"type": "subscribed", "symbols": symbols})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logger.warning("stream socket error: %s", exc)
        manager.disconnect(ws)
        try:
            await ws.close()
        except Exception:
            pass
