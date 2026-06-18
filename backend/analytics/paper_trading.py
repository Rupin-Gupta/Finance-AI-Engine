"""Paper trading engine — pure, no I/O. Executes virtual trades against real prices.

State is plain data so it's fully unit-testable:
  cash: float
  positions: {symbol: {"quantity": float, "avg_cost": float}}

Costs reuse the backtest CostModel (per-side slippage + half the round-trip fees).
No shorting: a SELL cannot exceed the held quantity.
"""
import math

from backend.analytics.backtest import CostModel


def execute_trade(
    cash: float,
    positions: dict,
    side: str,
    symbol: str,
    quantity: float,
    price: float,
    cost_model: CostModel | None = None,
) -> tuple[float, dict, dict]:
    """Apply one trade. Returns (new_cash, new_positions, trade_record).

    Raises ValueError on bad input, insufficient cash (BUY), or insufficient shares (SELL).
    """
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be positive")
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"invalid side: {side}")

    cm = cost_model or CostModel.for_symbol(symbol)
    notional = quantity * price
    fee = notional * cm.per_side_cost_fraction
    positions = {s: dict(p) for s, p in positions.items()}  # shallow copy, don't mutate caller
    pos = positions.get(symbol)

    if side == "BUY":
        total_cost = notional + fee
        if total_cost > cash + 1e-9:
            raise ValueError(f"insufficient cash: need {total_cost:.2f}, have {cash:.2f}")
        new_cash = cash - total_cost
        if pos:
            new_qty = pos["quantity"] + quantity
            new_avg = (pos["quantity"] * pos["avg_cost"] + notional) / new_qty
            positions[symbol] = {"quantity": new_qty, "avg_cost": new_avg}
        else:
            positions[symbol] = {"quantity": quantity, "avg_cost": price}
        realized = None
    else:  # SELL
        if not pos or pos["quantity"] + 1e-9 < quantity:
            held = pos["quantity"] if pos else 0
            raise ValueError(f"insufficient shares: selling {quantity}, hold {held}")
        proceeds = notional - fee
        new_cash = cash + proceeds
        realized = round((price - pos["avg_cost"]) * quantity - fee, 6)
        remaining = pos["quantity"] - quantity
        if remaining <= 1e-9:
            positions.pop(symbol, None)
        else:
            positions[symbol] = {"quantity": remaining, "avg_cost": pos["avg_cost"]}

    trade = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "fee": round(fee, 6),
        "realized_pnl": realized,
    }
    return round(new_cash, 6), positions, trade


def portfolio_metrics(
    cash: float, positions: dict, prices: dict, starting_cash: float
) -> dict:
    """Mark-to-market the portfolio. positions: {sym:{quantity,avg_cost}}, prices: {sym:last}."""
    positions_value = 0.0
    unrealized = 0.0
    priced = []
    for sym, p in positions.items():
        last = prices.get(sym)
        if last is None:
            continue
        mv = p["quantity"] * last
        positions_value += mv
        unrealized += p["quantity"] * (last - p["avg_cost"])
        priced.append(sym)

    equity = cash + positions_value
    total_return = (equity - starting_cash) / starting_cash if starting_cash else None
    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "equity": round(equity, 2),
        "unrealized_pnl": round(unrealized, 2),
        "total_return": round(total_return, 6) if total_return is not None else None,
        "starting_cash": round(starting_cash, 2),
        "unpriced_symbols": [s for s in positions if s not in priced],
    }


def plan_rebalance(
    recommendation: str,
    recommended_pct: float,
    equity: float,
    price: float,
    current_qty: float,
) -> dict | None:
    """Translate a decision + position-size target into a concrete BUY/SELL order (R1.1/R2.3).

    BUY: top up toward `recommended_pct × equity` (whole shares); never trims on a BUY.
    SELL: close the position (no shorting).
    HOLD / no edge / already at target: no order → None.

    Pure: the caller applies it via execute_trade and persists the result.
    """
    rec = (recommendation or "").upper()
    if price is None or price <= 0 or equity <= 0:
        return None

    if rec == "SELL":
        if current_qty > 0:
            return {"side": "SELL", "quantity": current_qty}
        return None

    if rec == "BUY" and recommended_pct and recommended_pct > 0:
        target_value = recommended_pct * equity
        target_qty = math.floor(target_value / price)
        delta = target_qty - current_qty
        if delta >= 1:
            return {"side": "BUY", "quantity": float(delta)}
    return None


def equity_curve_metrics(history: list[dict], trades: list[dict] | None = None) -> dict:
    """Risk/return metrics over the paper portfolio's equity history (R1.2).

    history: [{ts, equity}, ...] oldest→newest. trades (optional): realized rows for win rate.
    Sharpe is annualized assuming roughly one snapshot per trading day (~252/yr).
    """
    pts = [float(h["equity"]) for h in history if h.get("equity") is not None]
    if len(pts) < 2:
        return {"points": len(pts), "total_return": None, "sharpe": None,
                "max_drawdown": None, "win_rate": None, "best": None, "worst": None}

    rets = [(pts[i] - pts[i - 1]) / pts[i - 1] for i in range(1, len(pts)) if pts[i - 1]]
    total_return = (pts[-1] - pts[0]) / pts[0] if pts[0] else None

    sharpe = None
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        sd = var ** 0.5
        if sd > 0:
            sharpe = round((mean / sd) * math.sqrt(252), 4)

    peak = pts[0]
    max_dd = 0.0
    for e in pts:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)

    win_rate = None
    if trades:
        closed = [t for t in trades if t.get("realized_pnl") is not None]
        if closed:
            wins = sum(1 for t in closed if t["realized_pnl"] > 0)
            win_rate = round(wins / len(closed), 4)

    return {
        "points": len(pts),
        "total_return": round(total_return, 6) if total_return is not None else None,
        "sharpe": sharpe,
        "max_drawdown": round(max_dd, 6),
        "win_rate": win_rate,
        "best": round(max(rets), 6) if rets else None,
        "worst": round(min(rets), 6) if rets else None,
    }
