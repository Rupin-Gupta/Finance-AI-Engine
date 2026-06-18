"""India market-signal fetchers (P5) — async, best-effort, graceful.

Sources are free NSE endpoints. NSE has aggressive anti-bot protection (it requires a
browser User-Agent + a cookie primed from the homepage and blocks many datacenter IPs),
so EVERY fetch here is defensive: it returns None / [] on any failure rather than raising,
and the engine simply treats a missing sub-signal as neutral. Live behaviour must be
validated from the deployment's egress IP — these endpoints can change shape without notice.

Gift Nifty has no clean free JSON feed; its fetcher returns None until a source is wired,
and the composite India signal works fine on FII/DII + PCR alone.
"""
import asyncio
import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_NSE_HOME = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _NSE_HOME,
}
_TIMEOUT = 12.0


async def _nse_client() -> httpx.AsyncClient | None:
    """An httpx client with NSE cookies primed from the homepage. None if priming fails."""
    client = httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True)
    try:
        await client.get(_NSE_HOME)  # sets anti-bot cookies
        return client
    except Exception as exc:  # noqa: BLE001 — any network/anti-bot failure → graceful skip
        logger.warning("NSE cookie priming failed: %s", exc)
        await client.aclose()
        return None


async def _get_json(client: httpx.AsyncClient, path: str) -> dict | list | None:
    try:
        resp = await client.get(f"{_NSE_HOME}{path}")
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("NSE GET %s failed: %s", path, exc)
        return None


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def parse_fii_dii(payload) -> dict:
    """Extract {fii_net_cr, dii_net_cr} from NSE's fiidiiTradeReact payload. Pure."""
    out = {"fii_net_cr": None, "dii_net_cr": None}
    for entry in payload or []:
        cat = str(entry.get("category", "")).upper()
        net = _to_float(entry.get("netValue") or entry.get("net"))
        if "FII" in cat or "FPI" in cat:
            out["fii_net_cr"] = net
        elif "DII" in cat:
            out["dii_net_cr"] = net
    return out


def parse_pcr(payload) -> float | None:
    """Compute NIFTY PCR = ΣputOI / ΣcallOI from an option-chain-indices payload. Pure."""
    records = (payload or {}).get("records", {})
    rows = records.get("data") or []
    put_oi = call_oi = 0.0
    for r in rows:
        pe = r.get("PE") or {}
        ce = r.get("CE") or {}
        put_oi += _to_float(pe.get("openInterest")) or 0.0
        call_oi += _to_float(ce.get("openInterest")) or 0.0
    if call_oi <= 0:
        return None
    return round(put_oi / call_oi, 4)


async def fetch_fii_dii(client: httpx.AsyncClient) -> dict:
    return parse_fii_dii(await _get_json(client, "/api/fiidiiTradeReact"))


async def fetch_pcr(client: httpx.AsyncClient) -> float | None:
    return parse_pcr(await _get_json(client, "/api/option-chain-indices?symbol=NIFTY"))


async def fetch_gift_nifty() -> dict:
    """Placeholder: no reliable free Gift Nifty JSON. Returns neutral (None) gracefully."""
    return {"gift_nifty_pct": None, "gift_nifty_level": None}


async def fetch_india_market_context() -> dict:
    """Fetch all market-wide India signals for today. Always returns a dict (Nones on failure)."""
    base = {"date": date.today(), "fii_net_cr": None, "dii_net_cr": None,
            "pcr": None, "gift_nifty_pct": None, "gift_nifty_level": None, "source": "nse"}
    client = await _nse_client()
    if client is None:
        base["source"] = "unavailable"
        return base
    try:
        fii_dii, pcr, gift = await asyncio.gather(
            fetch_fii_dii(client), fetch_pcr(client), fetch_gift_nifty(),
        )
        base.update(fii_dii)
        base["pcr"] = pcr
        base.update(gift)
    finally:
        await client.aclose()
    return base


async def fetch_bulk_block_deals() -> list[dict]:
    """Best-effort NSE bulk-deals fetch. Returns [] on any failure (informational only)."""
    client = await _nse_client()
    if client is None:
        return []
    try:
        payload = await _get_json(client, "/api/historical/bulk-deals")
        rows = (payload or {}).get("data") or []
        out: list[dict] = []
        for r in rows:
            sym = r.get("symbol") or r.get("BD_SYMBOL")
            if not sym:
                continue
            buy_sell = str(r.get("buySell") or r.get("BD_BUY_SELL") or "").upper()
            side = "BUY" if buy_sell.startswith("B") else "SELL" if buy_sell.startswith("S") else None
            out.append({
                "deal_date": date.today(),
                "symbol": f"{sym}.NS",
                "client": r.get("clientName") or r.get("BD_CLIENT_NAME"),
                "side": side,
                "quantity": int(_to_float(r.get("quantityTraded") or r.get("BD_QTY_TRD")) or 0),
                "price": _to_float(r.get("watp") or r.get("BD_TP_WATP")),
                "deal_type": "bulk",
            })
        return out
    finally:
        await client.aclose()
