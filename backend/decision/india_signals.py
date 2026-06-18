"""India-specific market signals (P5) — pure scorers, no I/O.

Three freely-available, high-signal, under-used inputs, combined into ONE composite
overlay signal (`india_flow`) that the engine applies to Indian (.NS/.BO) symbols only:

  - FII/DII net flow: institutional money moving in/out of cash equity (₹ crore).
  - NSE Put-Call Ratio (PCR): options positioning, read CONTRARIAN at extremes
    (very high PCR = excessive hedging/bearishness → bullish; very low = complacency → bearish).
  - Gift Nifty: pre-market direction vs the prior close.

The composite is a market-wide tilt (same for every Indian name on a given day). It is a
separate weight from the 8 core SIGNAL_WEIGHTS, so the US engine and the weight-tuning /
calibration machinery (which operate over the 8) are unaffected.
"""
from backend.decision.signals import SignalResult

INDIA_SIGNAL_WEIGHT = 0.10
_LEVELS = (-1.0, -0.5, 0.0, 0.5, 1.0)


def _snap(x: float) -> float:
    return min(_LEVELS, key=lambda lv: abs(lv - x))


def score_fii_dii(fii_net_cr, dii_net_cr) -> float | None:
    """Net institutional cash-equity flow (FII + DII), ₹ crore → -1..+1. None if no data."""
    if fii_net_cr is None and dii_net_cr is None:
        return None
    net = (fii_net_cr or 0.0) + (dii_net_cr or 0.0)
    if net > 2000:
        return 1.0
    if net > 500:
        return 0.5
    if net < -2000:
        return -1.0
    if net < -500:
        return -0.5
    return 0.0


def score_pcr(pcr) -> float | None:
    """NIFTY put/call OI ratio → contrarian -1..+1. None if no data."""
    if pcr is None:
        return None
    if pcr > 1.4:
        return 1.0      # heavy put hedging → oversold/contrarian bullish
    if pcr > 1.1:
        return 0.5
    if pcr < 0.6:
        return -1.0     # complacent call buying → overbought/contrarian bearish
    if pcr < 0.8:
        return -0.5
    return 0.0


def score_gift_nifty(gift_nifty_pct) -> float | None:
    """Gift Nifty pre-market move (fraction vs prev close) → directional -1..+1. None if no data."""
    if gift_nifty_pct is None:
        return None
    if gift_nifty_pct > 0.005:
        return 1.0
    if gift_nifty_pct > 0.0015:
        return 0.5
    if gift_nifty_pct < -0.005:
        return -1.0
    if gift_nifty_pct < -0.0015:
        return -0.5
    return 0.0


def score_india_market(context: dict | None) -> SignalResult:
    """Combine the available India sub-signals into one `india_flow` SignalResult.

    Averages whatever sub-scores are present (missing inputs are skipped, not penalised),
    snaps to a 5-level score, and reports which components were used in the label.
    """
    w = INDIA_SIGNAL_WEIGHT
    if not context:
        return SignalResult("india_flow", 0.0, w, None, "neutral")

    parts = {
        "fii_dii": score_fii_dii(context.get("fii_net_cr"), context.get("dii_net_cr")),
        "pcr": score_pcr(context.get("pcr")),
        "gift_nifty": score_gift_nifty(context.get("gift_nifty_pct")),
    }
    active = {k: v for k, v in parts.items() if v is not None}
    if not active:
        return SignalResult("india_flow", 0.0, w, None, "no_data")

    avg = sum(active.values()) / len(active)
    score = _snap(avg)
    label = "+".join(sorted(active)) if score != 0 else "neutral"
    return SignalResult("india_flow", score, w, round(avg, 4), label)
