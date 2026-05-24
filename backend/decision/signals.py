"""Convert analytics + sentiment data into normalized signal scores (-1, 0, +1)."""
from dataclasses import dataclass, field


SIGNAL_WEIGHTS = {
    "rsi":        0.20,
    "trend":      0.20,
    "momentum":   0.15,
    "volatility": 0.15,
    "sentiment":  0.15,
    "forecast":   0.15,
}


@dataclass
class SignalResult:
    name: str
    score: float        # -1, 0, or +1
    weight: float
    value: float | None = None
    label: str = ""


def score_rsi(rsi: float | None) -> SignalResult:
    if rsi is None:
        return SignalResult("rsi", 0.0, SIGNAL_WEIGHTS["rsi"], None, "neutral")
    if rsi < 35:
        return SignalResult("rsi", 1.0, SIGNAL_WEIGHTS["rsi"], rsi, "oversold")
    if rsi > 65:
        return SignalResult("rsi", -1.0, SIGNAL_WEIGHTS["rsi"], rsi, "overbought")
    return SignalResult("rsi", 0.0, SIGNAL_WEIGHTS["rsi"], rsi, "neutral")


def score_trend(close: float | None, sma_20: float | None) -> SignalResult:
    if close is None or sma_20 is None:
        return SignalResult("trend", 0.0, SIGNAL_WEIGHTS["trend"], None, "neutral")
    if close > sma_20:
        return SignalResult("trend", 1.0, SIGNAL_WEIGHTS["trend"], close, "above_sma")
    if close < sma_20:
        return SignalResult("trend", -1.0, SIGNAL_WEIGHTS["trend"], close, "below_sma")
    return SignalResult("trend", 0.0, SIGNAL_WEIGHTS["trend"], close, "at_sma")


def score_momentum(momentum_10: float | None) -> SignalResult:
    if momentum_10 is None:
        return SignalResult("momentum", 0.0, SIGNAL_WEIGHTS["momentum"], None, "neutral")
    if momentum_10 > 0.02:
        return SignalResult("momentum", 1.0, SIGNAL_WEIGHTS["momentum"], momentum_10, "positive")
    if momentum_10 < -0.02:
        return SignalResult("momentum", -1.0, SIGNAL_WEIGHTS["momentum"], momentum_10, "negative")
    return SignalResult("momentum", 0.0, SIGNAL_WEIGHTS["momentum"], momentum_10, "flat")


def score_volatility(vol_20: float | None) -> SignalResult:
    if vol_20 is None:
        return SignalResult("volatility", 0.0, SIGNAL_WEIGHTS["volatility"], None, "neutral")
    if vol_20 < 0.25:
        return SignalResult("volatility", 1.0, SIGNAL_WEIGHTS["volatility"], vol_20, "low")
    if vol_20 > 0.45:
        return SignalResult("volatility", -1.0, SIGNAL_WEIGHTS["volatility"], vol_20, "extreme")
    return SignalResult("volatility", 0.0, SIGNAL_WEIGHTS["volatility"], vol_20, "moderate")


def score_sentiment(sentiment_score: float | None) -> SignalResult:
    if sentiment_score is None:
        return SignalResult("sentiment", 0.0, SIGNAL_WEIGHTS["sentiment"], None, "neutral")
    if sentiment_score > 0.3:
        return SignalResult("sentiment", 1.0, SIGNAL_WEIGHTS["sentiment"], sentiment_score, "positive")
    if sentiment_score < -0.2:
        return SignalResult("sentiment", -1.0, SIGNAL_WEIGHTS["sentiment"], sentiment_score, "negative")
    return SignalResult("sentiment", 0.0, SIGNAL_WEIGHTS["sentiment"], sentiment_score, "neutral")


def score_forecast(current_close: float | None, predicted_close: float | None) -> SignalResult:
    if current_close is None or predicted_close is None or current_close == 0:
        return SignalResult("forecast", 0.0, SIGNAL_WEIGHTS["forecast"], None, "neutral")
    pct_change = (predicted_close - current_close) / current_close
    if pct_change > 0.01:
        return SignalResult("forecast", 1.0, SIGNAL_WEIGHTS["forecast"], pct_change, "up")
    if pct_change < -0.01:
        return SignalResult("forecast", -1.0, SIGNAL_WEIGHTS["forecast"], pct_change, "down")
    return SignalResult("forecast", 0.0, SIGNAL_WEIGHTS["forecast"], pct_change, "flat")


def compute_all_signals(
    close: float | None,
    rsi: float | None,
    sma_20: float | None,
    momentum_10: float | None,
    vol_20: float | None,
    sentiment_score: float | None,
    predicted_close: float | None,
) -> list[SignalResult]:
    return [
        score_rsi(rsi),
        score_trend(close, sma_20),
        score_momentum(momentum_10),
        score_volatility(vol_20),
        score_sentiment(sentiment_score),
        score_forecast(close, predicted_close),
    ]
