"""P8: multi-timeframe signals — resample + per-timeframe recommendation + confluence.

The daily pipeline is reused unchanged: weekly/monthly bars are RESAMPLED from stored
daily OHLCV (no new storage), intraday is fetched on demand (yfinance) by the router.
Each timeframe runs the same `add_all_indicators` → `compute_all_signals` →
`make_recommendation`, so a 20-period SMA means 20 weeks on the weekly frame, etc.
Confluence across timeframes is the payoff: agreement = higher conviction.
"""
import pandas as pd

from backend.analytics.indicators import add_all_indicators
from backend.decision.signals import compute_all_signals
from backend.decision.engine import make_recommendation

# pandas resample rules per timeframe label
RESAMPLE_RULES = {"weekly": "W-FRI", "monthly": "ME"}

# Minimum bars needed for indicators (sma_20 / rsi_14 / vol_20) to be meaningful.
_MIN_BARS = 25


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate a daily OHLCV frame (DatetimeIndex) to a coarser bar."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    cols = {k: v for k, v in agg.items() if k in df.columns}
    out = df.resample(rule).agg(cols).dropna(subset=["close"])
    return out


def _ohlcv_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows (asyncpg records or dicts) → tz-naive daily OHLCV frame, float-typed."""
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    df = df.sort_values("timestamp").set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = df[c].astype(float)
    return df


def summarize_timeframe(df: pd.DataFrame, timeframe: str,
                        sentiment_score: float | None = None) -> dict | None:
    """Indicators → signals → recommendation for one already-resampled frame.

    Forecast + India overlay are daily-only, so they are neutral here; sentiment is
    shared from the daily pipeline. None when the frame has too few bars.
    """
    if df is None or len(df) < _MIN_BARS:
        return None
    enr = add_all_indicators(df)
    last = enr.iloc[-1]

    close = float(last["close"])
    volume_ratio = None
    if "volume" in enr.columns and len(enr) >= 20:
        avg_vol = float(enr["volume"].iloc[-20:].mean())
        if avg_vol > 0:
            volume_ratio = float(enr["volume"].iloc[-1]) / avg_vol

    def _g(col):
        v = last.get(col)
        return float(v) if v is not None and pd.notna(v) else None

    vol_20 = _g("volatility_20")
    signals = compute_all_signals(
        close, _g("rsi_14"), _g("sma_20"), _g("momentum_10"), vol_20,
        sentiment_score, None, ema_9=_g("ema_9"), ema_20=_g("ema_20"),
        volume_ratio=volume_ratio,
    )
    result = make_recommendation(signals, vol_20)
    return {
        "timeframe": timeframe,
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "weighted_score": result["weighted_score"],
        "risk_level": result["risk_level"],
        "close": round(close, 4),
        "bars": int(len(enr)),
    }


def confluence(summaries: list[dict]) -> dict:
    """Agreement across timeframes → an aligned verdict + strength."""
    valid = [s for s in summaries if s]
    if not valid:
        return {"aligned": None, "agreement": 0.0, "verdict": "INSUFFICIENT", "counts": {}}
    counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for s in valid:
        counts[s["recommendation"]] = counts.get(s["recommendation"], 0) + 1
    top = max(counts, key=counts.get)
    agreement = round(counts[top] / len(valid), 4)
    # Aligned only when every timeframe agrees and it's directional.
    aligned = counts[top] == len(valid) and top in ("BUY", "SELL")
    if aligned:
        verdict = f"STRONG_{top}"
    elif counts[top] == len(valid):
        verdict = "HOLD"
    elif agreement >= 0.5:
        verdict = f"LEANS_{top}"
    else:
        verdict = "MIXED"
    return {"aligned": aligned, "agreement": agreement, "verdict": verdict, "counts": counts}


def multi_timeframe_view(daily_rows: list[dict], sentiment_score: float | None = None,
                         intraday_rows: list[dict] | None = None) -> dict:
    """Daily (stored) + weekly + monthly (resampled) [+ intraday if supplied] + confluence."""
    daily = _ohlcv_frame(daily_rows)
    summaries: list[dict] = []

    if intraday_rows:
        intr = _ohlcv_frame(intraday_rows)
        s = summarize_timeframe(intr, "intraday", sentiment_score)
        if s:
            summaries.append(s)

    if not daily.empty:
        for tf, label in (("daily", None), ("weekly", "weekly"), ("monthly", "monthly")):
            frame = daily if tf == "daily" else resample_ohlcv(daily, RESAMPLE_RULES[tf])
            s = summarize_timeframe(frame, tf, sentiment_score)
            if s:
                summaries.append(s)

    return {"timeframes": summaries, "confluence": confluence(summaries)}
