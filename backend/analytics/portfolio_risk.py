"""R6: portfolio risk analytics — pure functions over positions + prices.

Answers "am I unknowingly taking huge sector/country/correlation risk?" for the
watchlist and the paper portfolio. Historical (non-parametric) VaR/CVaR — no
normality assumption; financial returns have fat tails.

All functions degrade gracefully: missing sector/cap data lands in "Unknown",
missing price history simply omits the correlation/VaR block.
"""
import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Concentration warning thresholds
_SECTOR_WARN_PCT = 0.40
_POSITION_WARN_PCT = 0.25
_CORR_WARN = 0.70

# Market-cap buckets (USD; Indian caps are reported in INR by yfinance but the
# bucket boundaries still rank within-market reasonably — refine in P9).
_LARGE_CAP = 10e9
_MID_CAP = 2e9


def position_weights(positions: list[dict]) -> dict[str, float]:
    """{symbol: weight} from [{symbol, value}]. Zero/negative total → empty."""
    total = sum(p["value"] for p in positions if p.get("value"))
    if total <= 0:
        return {}
    return {p["symbol"]: p["value"] / total for p in positions if p.get("value")}


def sector_exposure(positions: list[dict], sector_map: dict[str, str | None]) -> dict:
    """Per-sector weight + Herfindahl concentration (HHI ∈ (1/n, 1])."""
    weights = position_weights(positions)
    by_sector: dict[str, float] = {}
    for sym, w in weights.items():
        sector = sector_map.get(sym) or "Unknown"
        by_sector[sector] = by_sector.get(sector, 0.0) + w
    hhi = sum(w * w for w in by_sector.values())
    top = max(by_sector.items(), key=lambda kv: kv[1]) if by_sector else (None, 0.0)
    return {
        "by_sector": {k: round(v, 4) for k, v in sorted(by_sector.items(), key=lambda kv: -kv[1])},
        "hhi": round(hhi, 4),
        "top_sector": top[0],
        "top_sector_pct": round(top[1], 4),
    }


def country_exposure(positions: list[dict]) -> dict:
    """US vs India split from the symbol suffix convention (.NS/.BO = India)."""
    weights = position_weights(positions)
    india = sum(w for s, w in weights.items() if s.endswith((".NS", ".BO")))
    return {"US": round(1.0 - india, 4), "INDIA": round(india, 4)}


def market_cap_exposure(positions: list[dict], cap_map: dict[str, float | None]) -> dict:
    weights = position_weights(positions)
    buckets = {"large": 0.0, "mid": 0.0, "small": 0.0, "unknown": 0.0}
    for sym, w in weights.items():
        cap = cap_map.get(sym)
        if cap is None:
            buckets["unknown"] += w
        elif cap >= _LARGE_CAP:
            buckets["large"] += w
        elif cap >= _MID_CAP:
            buckets["mid"] += w
        else:
            buckets["small"] += w
    return {k: round(v, 4) for k, v in buckets.items()}


def _portfolio_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series | None:
    """Daily weighted portfolio returns from a close-price DataFrame (cols=symbols)."""
    cols = [s for s in weights if s in prices.columns]
    if not cols or len(prices) < 21:
        return None
    rets = prices[cols].pct_change().dropna()
    if rets.empty:
        return None
    w = np.array([weights[s] for s in cols])
    w = w / w.sum()  # renormalize over priced symbols only
    return pd.Series(rets.values @ w, index=rets.index)


def correlation_metrics(prices: pd.DataFrame, weights: dict[str, float]) -> dict | None:
    """Average + max pairwise correlation of held symbols (needs ≥2 priced)."""
    cols = [s for s in weights if s in prices.columns]
    if len(cols) < 2 or len(prices) < 21:
        return None
    corr = prices[cols].pct_change().dropna().corr()
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            c = corr.loc[a, b]
            if not math.isnan(c):
                pairs.append((a, b, float(c)))
    if not pairs:
        return None
    avg = sum(c for _, _, c in pairs) / len(pairs)
    a, b, mx = max(pairs, key=lambda p: p[2])
    return {
        "avg_pairwise": round(avg, 4),
        "max_pair": {"symbols": [a, b], "correlation": round(mx, 4)},
        "matrix": {x: {y: round(float(corr.loc[x, y]), 4) for y in cols} for x in cols},
    }


def var_cvar(prices: pd.DataFrame, weights: dict[str, float], total_value: float,
             confidence: float = 0.95) -> dict | None:
    """Historical 1-day VaR + CVaR (expected shortfall) at the given confidence."""
    rets = _portfolio_returns(prices, weights)
    if rets is None or len(rets) < 20:
        return None
    q = np.percentile(rets, (1.0 - confidence) * 100)
    tail = rets[rets <= q]
    var_pct = round(max(-float(q), 0.0), 4)
    cvar_pct = round(max(-float(tail.mean()), 0.0) if len(tail) else var_pct, 4)
    ann_vol = float(rets.std() * math.sqrt(TRADING_DAYS))
    return {
        "confidence": confidence,
        "horizon_days": 1,
        "var_pct": var_pct,
        "cvar_pct": cvar_pct,
        "var_value": round(var_pct * total_value, 2),
        "cvar_value": round(cvar_pct * total_value, 2),
        "annualized_vol": round(ann_vol, 4),
        "observations": int(len(rets)),
    }


def risk_score(sector: dict, corr: dict | None, var: dict | None) -> dict:
    """Composite 0–100 (higher = riskier): concentration + correlation + volatility.

    Components are each mapped to [0, 1] then averaged over whichever are
    available, so sparse data never inflates or deflates the score.
    """
    components: dict[str, float] = {}
    # HHI: 0.1 (well spread) … 1.0 (single name) → scaled
    components["concentration"] = min(max((sector["hhi"] - 0.1) / 0.9, 0.0), 1.0)
    if corr is not None:
        components["correlation"] = min(max(corr["avg_pairwise"], 0.0), 1.0)
    if var is not None:
        # 40% annualized vol ≈ very risky for a portfolio
        components["volatility"] = min(var["annualized_vol"] / 0.40, 1.0)
    score = round(100 * sum(components.values()) / len(components), 1)
    if score >= 75:
        level = "Extreme"
    elif score >= 50:
        level = "High"
    elif score >= 25:
        level = "Medium"
    else:
        level = "Low"
    return {"score": score, "level": level,
            "components": {k: round(v, 4) for k, v in components.items()}}


def build_warnings(positions: list[dict], sector: dict, corr: dict | None,
                   var: dict | None) -> list[str]:
    warnings: list[str] = []
    if sector["top_sector"] and sector["top_sector"] != "Unknown" and sector["top_sector_pct"] > _SECTOR_WARN_PCT:
        warnings.append(
            f"{sector['top_sector']} is {sector['top_sector_pct']:.0%} of the portfolio — over-concentrated (>{_SECTOR_WARN_PCT:.0%})."
        )
    for sym, w in position_weights(positions).items():
        if w > _POSITION_WARN_PCT:
            warnings.append(f"{sym} alone is {w:.0%} of the portfolio (>{_POSITION_WARN_PCT:.0%}).")
    if corr is not None and corr["avg_pairwise"] > _CORR_WARN:
        warnings.append(
            f"Average pairwise correlation {corr['avg_pairwise']:.2f} — positions move together; diversification is weak."
        )
    if var is not None and var["cvar_pct"] > 0.05:
        warnings.append(
            f"1-day CVaR {var['cvar_pct']:.1%}: a bad day in the worst {1 - var['confidence']:.0%} tail averages that loss."
        )
    return warnings


def assess_portfolio_risk(
    positions: list[dict],
    sector_map: dict[str, str | None],
    cap_map: dict[str, float | None],
    prices: pd.DataFrame,
    confidence: float = 0.95,
) -> dict:
    """Full R6 report for [{symbol, value}] positions."""
    positions = [p for p in positions if p.get("value") and p["value"] > 0]
    if not positions:
        return {"positions": 0, "total_value": 0.0, "warnings": ["No valued positions to assess."]}

    total_value = float(sum(p["value"] for p in positions))
    weights = position_weights(positions)
    sector = sector_exposure(positions, sector_map)
    corr = correlation_metrics(prices, weights)
    var = var_cvar(prices, weights, total_value, confidence=confidence)

    return {
        "positions": len(positions),
        "total_value": round(total_value, 2),
        "weights": {s: round(w, 4) for s, w in sorted(weights.items(), key=lambda kv: -kv[1])},
        "sector_exposure": sector,
        "country_exposure": country_exposure(positions),
        "market_cap_exposure": market_cap_exposure(positions, cap_map),
        "correlation": corr,
        "var": var,
        "risk_score": risk_score(sector, corr, var),
        "warnings": build_warnings(positions, sector, corr, var),
    }
