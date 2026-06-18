import asyncio
from typing import Literal

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252
_EF_POINTS = 40

Objective = Literal["min_variance", "max_sharpe", "efficient_frontier"]


def _portfolio_stats(weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray, rf: float):
    ret = float(np.dot(weights, mean_returns) * TRADING_DAYS)
    vol = float(np.sqrt(np.dot(weights, cov @ weights) * TRADING_DAYS))
    sharpe = (ret - rf) / vol if vol > 1e-10 else 0.0
    return ret, vol, sharpe


def _optimize(mean_returns: np.ndarray, cov: np.ndarray, rf: float, objective: Objective):
    n = len(mean_returns)
    bounds = tuple((0.0, 1.0) for _ in range(n))
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    w0 = np.ones(n) / n

    if objective == "min_variance":
        def neg_fn(w):
            return float(np.dot(w, cov @ w) * TRADING_DAYS)
        res = minimize(neg_fn, w0, method="SLSQP", bounds=bounds, constraints=constraints,
                       options={"ftol": 1e-9, "maxiter": 1000})

    elif objective in ("max_sharpe", "efficient_frontier"):
        def neg_sharpe(w):
            ret = float(np.dot(w, mean_returns) * TRADING_DAYS)
            vol = float(np.sqrt(np.dot(w, cov @ w) * TRADING_DAYS))
            return -(ret - rf) / vol if vol > 1e-10 else 0.0
        res = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds, constraints=constraints,
                       options={"ftol": 1e-9, "maxiter": 1000})

    else:
        raise ValueError(f"Unknown objective: {objective}")

    return res.x if res.success else w0


def _efficient_frontier(mean_returns: np.ndarray, cov: np.ndarray, rf: float) -> list[dict]:
    n = len(mean_returns)
    bounds = tuple((0.0, 1.0) for _ in range(n))
    w0 = np.ones(n) / n

    ann_returns = mean_returns * TRADING_DAYS
    min_ret = float(np.min(ann_returns))
    max_ret = float(np.max(ann_returns))
    targets = np.linspace(min_ret, max_ret, _EF_POINTS)
    points = []

    for target in targets:
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {"type": "eq", "fun": lambda w, t=target: float(np.dot(w, ann_returns)) - t},
        ]
        res = minimize(
            lambda w: float(np.dot(w, cov @ w) * TRADING_DAYS),
            w0, method="SLSQP", bounds=bounds, constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 500},
        )
        if res.success:
            vol = float(np.sqrt(res.fun))
            points.append({"return": round(target, 6), "volatility": round(vol, 6)})

    return points


def optimize_portfolio(
    prices_df: pd.DataFrame,
    objective: Objective,
    risk_free_rate: float,
) -> dict:
    """
    prices_df: DataFrame with DatetimeIndex, columns = symbols, values = close prices.
    Returns weights, metrics, and efficient frontier.
    """
    log_returns = np.log(prices_df / prices_df.shift(1)).dropna()

    if len(log_returns) < 20:
        raise ValueError(f"Insufficient data: {len(log_returns)} days after aligning symbols")

    mean_returns = log_returns.mean().values
    cov = log_returns.cov().values
    symbols = list(prices_df.columns)

    weights = _optimize(mean_returns, cov, risk_free_rate, objective)
    ret, vol, sharpe = _portfolio_stats(weights, mean_returns, cov, risk_free_rate)

    ef_points = []
    if len(symbols) > 1:
        ef_points = _efficient_frontier(mean_returns, cov, risk_free_rate)

    weights_dict = {sym: round(float(w), 6) for sym, w in zip(symbols, weights)}

    return {
        "weights": weights_dict,
        "metrics": {
            "expected_annual_return": round(ret, 6),
            "annual_volatility": round(vol, 6),
            "sharpe_ratio": round(sharpe, 6),
        },
        "efficient_frontier": ef_points,
        "data_points": len(log_returns),
    }


async def optimize_portfolio_async(
    prices_df: pd.DataFrame,
    objective: Objective,
    risk_free_rate: float,
) -> dict:
    return await asyncio.to_thread(optimize_portfolio, prices_df, objective, risk_free_rate)
