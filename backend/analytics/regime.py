"""R5: market regime detection — pure classification + regime-aware weight tilts.

Features per market (US / INDIA): index trend (close vs SMA50/SMA200), volatility
(VIX level, realized index vol fallback), and market breadth (share of tracked
symbols above their 20-bar-ago close). All inputs optional — missing data degrades
gracefully toward 'sideways', never errors.

Pure functions only; fetching/persistence live in the regime_run job and
db/queries/regime.py.
"""
import math

REGIME_BULL = "bull"
REGIME_BEAR = "bear"
REGIME_HIGH_VOL = "high_vol"
REGIME_SIDEWAYS = "sideways"

REGIMES = (REGIME_BULL, REGIME_BEAR, REGIME_HIGH_VOL, REGIME_SIDEWAYS)

# Index symbols + volatility gauges per market (yfinance tickers).
MARKET_INDEXES = {
    "US": {"index": "SPY", "vix": "^VIX"},
    "INDIA": {"index": "^NSEI", "vix": "^INDIAVIX"},
}

# High-vol triggers: VIX gauge level, or annualized realized index vol.
_VIX_HIGH = 28.0
_REALIZED_VOL_HIGH = 0.30

# Breadth confirmation thresholds (share of symbols advancing over 20 bars).
_BREADTH_BULL = 0.55
_BREADTH_BEAR = 0.45

_TRADING_DAYS = 252

# Regime-aware weight tilts (R5 composes with R4 tuned weights): multiply, then
# renormalize to the base sum so the weighted-score scale (and the ±0.30 engine
# thresholds) stay meaningful. Momentum-following favored in bull, mean-reversion
# (RSI) in sideways, caution signals (volatility, sentiment) in bear/high-vol.
REGIME_WEIGHT_TILTS: dict[str, dict[str, float]] = {
    REGIME_BULL: {"momentum": 1.3, "trend": 1.25, "ema_crossover": 1.2, "rsi": 0.7, "volatility": 0.9},
    REGIME_BEAR: {"sentiment": 1.25, "volatility": 1.25, "trend": 1.15, "momentum": 0.8, "forecast": 0.85},
    REGIME_SIDEWAYS: {"rsi": 1.4, "volatility": 1.1, "momentum": 0.7, "trend": 0.75, "ema_crossover": 0.85},
    REGIME_HIGH_VOL: {"volatility": 1.3, "sentiment": 1.15, "momentum": 0.85, "forecast": 0.8, "ema_crossover": 0.9},
}

# Market-level confidence cap: in a high-vol regime every signal is less reliable
# (mirrors the per-symbol extreme-vol cap in engine.py).
HIGH_VOL_CONF_CAP = 0.75


def compute_regime_features(closes: list[float]) -> dict:
    """Trend + realized-vol features from an index's daily closes (oldest first)."""
    out: dict = {"index_close": None, "sma_50": None, "sma_200": None, "realized_vol": None}
    closes = [float(c) for c in closes if c is not None]
    if not closes:
        return out
    out["index_close"] = closes[-1]
    if len(closes) >= 50:
        out["sma_50"] = sum(closes[-50:]) / 50
    if len(closes) >= 200:
        out["sma_200"] = sum(closes[-200:]) / 200
    if len(closes) >= 21:
        rets = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(len(closes) - 20, len(closes))
            if closes[i - 1] != 0
        ]
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            out["realized_vol"] = math.sqrt(var) * math.sqrt(_TRADING_DAYS)
    return out


def classify_regime(
    index_close: float | None,
    sma_50: float | None,
    sma_200: float | None,
    vix: float | None = None,
    realized_vol: float | None = None,
    breadth_pct: float | None = None,
) -> dict:
    """Rule-based regime classification. Returns {regime, reason}.

    Order matters: high-vol dominates (a volatile bull is still treacherous),
    then trend alignment decides bull/bear, breadth confirms or demotes,
    everything else is sideways.
    """
    if vix is not None and vix > _VIX_HIGH:
        return {"regime": REGIME_HIGH_VOL, "reason": f"VIX {vix:.1f} > {_VIX_HIGH:.0f}"}
    if realized_vol is not None and realized_vol > _REALIZED_VOL_HIGH:
        return {"regime": REGIME_HIGH_VOL, "reason": f"realized index vol {realized_vol:.2f} > {_REALIZED_VOL_HIGH:.2f}"}

    if index_close is None or sma_50 is None:
        return {"regime": REGIME_SIDEWAYS, "reason": "insufficient index history"}

    above_50 = index_close > sma_50
    above_200 = sma_200 is None or index_close > sma_200  # no SMA200 → lean on SMA50
    below_200 = sma_200 is not None and index_close < sma_200

    if above_50 and above_200:
        if breadth_pct is not None and breadth_pct < _BREADTH_BEAR:
            return {"regime": REGIME_SIDEWAYS, "reason": f"uptrend but breadth {breadth_pct:.0%} weak"}
        return {"regime": REGIME_BULL, "reason": "close above SMA50 and SMA200"}

    if not above_50 and below_200:
        if breadth_pct is not None and breadth_pct > _BREADTH_BULL:
            return {"regime": REGIME_SIDEWAYS, "reason": f"downtrend but breadth {breadth_pct:.0%} strong"}
        return {"regime": REGIME_BEAR, "reason": "close below SMA50 and SMA200"}

    return {"regime": REGIME_SIDEWAYS, "reason": "mixed trend signals"}


def regime_adjusted_weights(base: dict, regime: str | None) -> dict:
    """Tilt signal weights for the regime, renormalized to the base sum.

    Unknown/None regime → base unchanged. Signals without a tilt keep their
    weight (pre-normalization). Composes with R4: base may be the tuned set.
    """
    if not regime or regime not in REGIME_WEIGHT_TILTS or not base:
        return dict(base) if base else {}
    tilts = REGIME_WEIGHT_TILTS[regime]
    tilted = {name: w * tilts.get(name, 1.0) for name, w in base.items()}
    base_sum = sum(base.values())
    tilted_sum = sum(tilted.values())
    if tilted_sum <= 0:
        return dict(base)
    factor = base_sum / tilted_sum
    return {name: w * factor for name, w in tilted.items()}


def market_for_symbol(symbol: str) -> str:
    return "INDIA" if symbol.endswith((".NS", ".BO")) else "US"
