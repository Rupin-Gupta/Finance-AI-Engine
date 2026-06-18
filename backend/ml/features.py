"""P14: feature engineering for the ML directional signal — strictly as-of, no lookahead.

Features are stationary ratios derived from already-computed analytics + sentiment at
date d. The LABEL is the forward N-day return crossing a threshold — it uses future
prices, so a row is only labellable when that future bar exists; at inference time we
build the feature row WITHOUT a label. Features and labels are never mixed in time.
"""
from datetime import date, datetime, timedelta

# Fixed feature order — persisted with the model; inference must match exactly.
FEATURE_NAMES = ["rsi", "trend_dev", "momentum", "volatility", "ema_gap", "sentiment"]


def _f(v):
    return float(v) if v is not None else None


def _as_date(v):
    # datetime is a subclass of date — check it FIRST and normalize to a pure date.
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def build_feature_vector(rsi, sma_20, close, momentum, volatility,
                         ema_9, ema_20, sentiment) -> list[float | None]:
    """One feature row in FEATURE_NAMES order. Missing inputs → None (HGB handles NaN)."""
    rsi, sma_20, close = _f(rsi), _f(sma_20), _f(close)
    momentum, volatility = _f(momentum), _f(volatility)
    ema_9, ema_20, sentiment = _f(ema_9), _f(ema_20), _f(sentiment)
    trend_dev = (close - sma_20) / sma_20 if (close is not None and sma_20) else None
    ema_gap = (ema_9 - ema_20) / ema_20 if (ema_9 is not None and ema_20) else None
    return [rsi, trend_dev, momentum, volatility, ema_gap,
            sentiment if sentiment is not None else 0.0]


def build_dataset(analytics_rows: list[dict], closes_by_date: dict,
                  sentiment_by_date: dict, horizon: int = 5,
                  threshold: float = 0.0) -> tuple[list[list], list[int], list]:
    """(X, y, dates) for one symbol. Rows are labelled only when the future bar exists.

    closes_by_date / sentiment_by_date keyed by date. Label = 1 if
    close[d+horizon]/close[d] - 1 > threshold else 0.
    """
    X, y, dates = [], [], []
    for r in analytics_rows:
        d = _as_date(r.get("timestamp"))
        if d is None:
            continue
        close = closes_by_date.get(d)
        if close is None:
            continue
        future = closes_by_date.get(d + timedelta(days=horizon))
        if future is None:
            # search forward up to a few days for the next available trading bar
            for k in range(horizon, horizon + 4):
                future = closes_by_date.get(d + timedelta(days=k))
                if future is not None:
                    break
        if future is None or close <= 0:
            continue  # cannot label without a future price — excluded, never guessed
        vec = build_feature_vector(
            r.get("rsi_14"), r.get("sma_20"), close, r.get("momentum_10"),
            r.get("volatility_20"), r.get("ema_9"), r.get("ema_20"),
            sentiment_by_date.get(d),
        )
        X.append(vec)
        y.append(1 if (future / close - 1.0) > threshold else 0)
        dates.append(d)
    return X, y, dates
