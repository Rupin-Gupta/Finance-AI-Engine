"""Convert analytics + sentiment data into 5-level signal scores (-1, -0.5, 0, +0.5, +1)."""
from dataclasses import dataclass


# 8 signals — weights sum to 1.0.
# ema_crossover (EMA9 vs EMA20) and volume (volume_ratio × direction) are new.
# Earnings proximity is a confidence gate in engine.py, not a scored signal.
SIGNAL_WEIGHTS = {
    "rsi":           0.12,
    "trend":         0.16,
    "momentum":      0.12,
    "volatility":    0.08,
    "sentiment":     0.22,
    "forecast":      0.12,
    "ema_crossover": 0.10,
    "volume":        0.08,
}


@dataclass
class SignalResult:
    name: str
    score: float        # -1.0, -0.5, 0.0, +0.5, or +1.0
    weight: float
    value: float | None = None
    label: str = ""


def score_rsi(rsi: float | None) -> SignalResult:
    w = SIGNAL_WEIGHTS["rsi"]
    if rsi is None:
        return SignalResult("rsi", 0.0, w, None, "neutral")
    if rsi < 25:
        return SignalResult("rsi", 1.0, w, rsi, "deeply_oversold")
    if rsi < 35:
        return SignalResult("rsi", 0.5, w, rsi, "oversold")
    if rsi > 75:
        return SignalResult("rsi", -1.0, w, rsi, "deeply_overbought")
    if rsi > 65:
        return SignalResult("rsi", -0.5, w, rsi, "overbought")
    return SignalResult("rsi", 0.0, w, rsi, "neutral")


def score_trend(close: float | None, sma_20: float | None) -> SignalResult:
    w = SIGNAL_WEIGHTS["trend"]
    if close is None or sma_20 is None or sma_20 == 0:
        return SignalResult("trend", 0.0, w, None, "neutral")
    deviation = (close - sma_20) / sma_20
    if deviation > 0.03:
        return SignalResult("trend", 1.0, w, close, "strong_uptrend")
    if deviation > 0:
        return SignalResult("trend", 0.5, w, close, "above_sma")
    if deviation < -0.03:
        return SignalResult("trend", -1.0, w, close, "strong_downtrend")
    if deviation < 0:
        return SignalResult("trend", -0.5, w, close, "below_sma")
    return SignalResult("trend", 0.0, w, close, "at_sma")


def score_momentum(momentum_10: float | None) -> SignalResult:
    w = SIGNAL_WEIGHTS["momentum"]
    if momentum_10 is None:
        return SignalResult("momentum", 0.0, w, None, "neutral")
    if momentum_10 > 0.05:
        return SignalResult("momentum", 1.0, w, momentum_10, "strong_positive")
    if momentum_10 > 0.02:
        return SignalResult("momentum", 0.5, w, momentum_10, "positive")
    if momentum_10 < -0.05:
        return SignalResult("momentum", -1.0, w, momentum_10, "strong_negative")
    if momentum_10 < -0.02:
        return SignalResult("momentum", -0.5, w, momentum_10, "negative")
    return SignalResult("momentum", 0.0, w, momentum_10, "flat")


def score_volatility(vol_20: float | None) -> SignalResult:
    w = SIGNAL_WEIGHTS["volatility"]
    if vol_20 is None:
        return SignalResult("volatility", 0.0, w, None, "neutral")
    if vol_20 < 0.15:
        return SignalResult("volatility", 1.0, w, vol_20, "very_low")
    if vol_20 < 0.25:
        return SignalResult("volatility", 0.5, w, vol_20, "low")
    if vol_20 < 0.35:
        return SignalResult("volatility", 0.0, w, vol_20, "normal")
    if vol_20 < 0.45:
        return SignalResult("volatility", -0.5, w, vol_20, "elevated")
    return SignalResult("volatility", -1.0, w, vol_20, "extreme")


def score_sentiment(sentiment_score: float | None) -> SignalResult:
    """
    5-level sentiment scoring.
    Thresholds tightened vs. v1 because the 6-source count-weighted aggregate
    is more reliable than single-source Yahoo RSS.
    """
    w = SIGNAL_WEIGHTS["sentiment"]
    if sentiment_score is None:
        return SignalResult("sentiment", 0.0, w, None, "neutral")
    if sentiment_score > 0.40:
        return SignalResult("sentiment", 1.0, w, sentiment_score, "strongly_positive")
    if sentiment_score > 0.15:
        return SignalResult("sentiment", 0.5, w, sentiment_score, "positive")
    if sentiment_score < -0.30:
        return SignalResult("sentiment", -1.0, w, sentiment_score, "strongly_negative")
    if sentiment_score < -0.15:
        return SignalResult("sentiment", -0.5, w, sentiment_score, "negative")
    return SignalResult("sentiment", 0.0, w, sentiment_score, "neutral")


def score_forecast(current_close: float | None, predicted_close: float | None) -> SignalResult:
    w = SIGNAL_WEIGHTS["forecast"]
    if current_close is None or predicted_close is None or current_close == 0:
        return SignalResult("forecast", 0.0, w, None, "neutral")
    pct = (predicted_close - current_close) / current_close
    if pct > 0.03:
        return SignalResult("forecast", 1.0, w, pct, "strong_up")
    if pct > 0.01:
        return SignalResult("forecast", 0.5, w, pct, "up")
    if pct < -0.03:
        return SignalResult("forecast", -1.0, w, pct, "strong_down")
    if pct < -0.01:
        return SignalResult("forecast", -0.5, w, pct, "down")
    return SignalResult("forecast", 0.0, w, pct, "flat")


def score_ema_crossover(ema_9: float | None, ema_20: float | None) -> SignalResult:
    """EMA9 (fast) vs EMA20 (slow). Positive gap = momentum accelerating."""
    w = SIGNAL_WEIGHTS["ema_crossover"]
    if ema_9 is None or ema_20 is None or ema_20 == 0:
        return SignalResult("ema_crossover", 0.0, w, None, "neutral")
    pct = (ema_9 - ema_20) / ema_20
    if pct > 0.02:
        return SignalResult("ema_crossover", 1.0, w, pct, "strong_bullish_cross")
    if pct > 0.005:
        return SignalResult("ema_crossover", 0.5, w, pct, "bullish_cross")
    if pct < -0.02:
        return SignalResult("ema_crossover", -1.0, w, pct, "strong_bearish_cross")
    if pct < -0.005:
        return SignalResult("ema_crossover", -0.5, w, pct, "bearish_cross")
    return SignalResult("ema_crossover", 0.0, w, pct, "neutral")


def score_volume(volume_ratio: float | None, momentum_10: float | None) -> SignalResult:
    """
    High volume confirms the prevailing price direction.
    volume_ratio = current_volume / 20-day avg_volume.
    Direction borrowed from momentum_10 sign.
    """
    w = SIGNAL_WEIGHTS["volume"]
    if volume_ratio is None:
        return SignalResult("volume", 0.0, w, None, "neutral")
    direction = 1 if (momentum_10 or 0) >= 0 else -1
    if volume_ratio > 2.0:
        score = 1.0 * direction
        label = "high_vol_up" if direction > 0 else "high_vol_down"
    elif volume_ratio > 1.4:
        score = 0.5 * direction
        label = "above_avg_up" if direction > 0 else "above_avg_down"
    elif volume_ratio < 0.6:
        score = 0.0
        label = "low_volume"
    else:
        score = 0.0
        label = "neutral"
    return SignalResult("volume", score, w, volume_ratio, label)


# P14: ML directional signal — appended ONLY when a promoted model produced a prob.
# Kept off SIGNAL_WEIGHTS (like india_flow) so the 8-signal engine + R4 tuning +
# calibration are untouched; the model's edge is proven OOS before it ever contributes.
ML_SIGNAL_WEIGHT = 0.10


def score_ml(prob: float | None) -> SignalResult:
    """P(up over horizon) → graduated directional score. 0.5 = no edge = neutral."""
    w = ML_SIGNAL_WEIGHT
    if prob is None:
        return SignalResult("ml", 0.0, w, None, "neutral")
    if prob > 0.65:
        return SignalResult("ml", 1.0, w, prob, "strong_up")
    if prob > 0.55:
        return SignalResult("ml", 0.5, w, prob, "up")
    if prob < 0.35:
        return SignalResult("ml", -1.0, w, prob, "strong_down")
    if prob < 0.45:
        return SignalResult("ml", -0.5, w, prob, "down")
    return SignalResult("ml", 0.0, w, prob, "neutral")


def compute_all_signals(
    close: float | None,
    rsi: float | None,
    sma_20: float | None,
    momentum_10: float | None,
    vol_20: float | None,
    sentiment_score: float | None,
    predicted_close: float | None,
    ema_9: float | None = None,
    ema_20: float | None = None,
    volume_ratio: float | None = None,
    weights: dict | None = None,
    india_context: dict | None = None,
    ml_prob: float | None = None,
) -> list[SignalResult]:
    signals = [
        score_rsi(rsi),
        score_trend(close, sma_20),
        score_momentum(momentum_10),
        score_volatility(vol_20),
        score_sentiment(sentiment_score),
        score_forecast(close, predicted_close),
        score_ema_crossover(ema_9, ema_20),
        score_volume(volume_ratio, momentum_10),
    ]
    # Optional auto-tuned weight override (R4); defaults to each signal's SIGNAL_WEIGHTS value.
    if weights:
        for s in signals:
            if s.name in weights:
                s.weight = float(weights[s.name])

    # P5: India market overlay — appended only for Indian symbols (caller passes context).
    # Separate weight (INDIA_SIGNAL_WEIGHT), so the 8-signal US engine + weight tuning are
    # untouched. Imported lazily to avoid a circular import (india_signals imports SignalResult).
    if india_context is not None:
        from backend.decision.india_signals import score_india_market
        signals.append(score_india_market(india_context))

    # P14: ML overlay — appended only when a promoted model returned a probability.
    if ml_prob is not None:
        signals.append(score_ml(ml_prob))
    return signals
