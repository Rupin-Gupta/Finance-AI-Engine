"""GET /v1/options/{symbol} — live options chain via yfinance."""
import asyncio
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_symbol

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])

_CHAIN_COLS = [
    "strike", "lastPrice", "bid", "ask",
    "volume", "openInterest", "impliedVolatility", "inTheMoney",
]


def _df_to_rows(df) -> list[dict]:
    available = [c for c in _CHAIN_COLS if c in df.columns]
    rows = []
    for _, row in df[available].iterrows():
        r = {}
        for col in available:
            val = row[col]
            if hasattr(val, "item"):
                val = val.item()
            if isinstance(val, float) and math.isnan(val):
                val = None
            r[col] = val
        rows.append(r)
    return rows


@router.get("/{symbol}")
@limiter.limit("20/minute")
async def get_options_chain(
    request: Request,
    symbol: str,
    expiry: str | None = Query(
        default=None,
        description="Expiry date (YYYY-MM-DD). Defaults to nearest expiration.",
    ),
):
    sym = validate_symbol(symbol)

    def _fetch():
        import yfinance as yf

        ticker = yf.Ticker(sym)
        expiries = ticker.options
        if not expiries:
            return None, [], None
        selected = expiry if (expiry and expiry in expiries) else expiries[0]
        chain = ticker.option_chain(selected)
        return selected, list(expiries), chain

    try:
        selected, expiries, chain = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("options fetch failed for %s: %s", sym, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch options for {sym}: {exc}")

    if chain is None:
        raise HTTPException(status_code=404, detail=f"No options data available for {sym}")

    return {
        "symbol": sym,
        "expiry": selected,
        "expiries": expiries,
        "calls": _df_to_rows(chain.calls),
        "puts": _df_to_rows(chain.puts),
    }
