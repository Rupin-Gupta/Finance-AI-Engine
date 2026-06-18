import ipaddress
import re
from urllib.parse import urlparse

from fastapi import HTTPException

# Supports US tickers (AAPL, BRK-B), Indian NSE (RELIANCE.NS, M&M.NS, BAJAJ-AUTO.NS, 3MINDIA.NS)
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}(\.(NS|BO))?$")

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def validated_symbol(symbol: str) -> str:
    """Dependency form of validate_symbol for the {symbol} path param.

    Declare before any DB dependency so invalid symbols return 422 without
    acquiring a connection.
    """
    return validate_symbol(symbol)


def validate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid symbol: {symbol!r}. "
                "Use US tickers (AAPL, BRK-B) or Indian NSE tickers with .NS suffix (RELIANCE.NS, M&M.NS)."
            ),
        )
    return s


def validate_ingest_url(url: str) -> str:
    """Reject non-http/https schemes and private/loopback IP targets (SSRF guard)."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=422, detail="Malformed URL")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http/https URLs are allowed")

    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(status_code=422, detail="URL must have a hostname")

    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(status_code=422, detail="URL targets a disallowed host")

    try:
        addr = ipaddress.ip_address(hostname)
        if any(addr in net for net in _PRIVATE_NETS):
            raise HTTPException(status_code=422, detail="URL targets a private/reserved address")
    except ValueError:
        pass  # hostname is a domain name, not an IP — allow it

    return url
