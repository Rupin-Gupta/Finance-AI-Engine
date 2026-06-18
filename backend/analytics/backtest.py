"""Replay historical signals day-by-day → realistic, cost-adjusted P&L metrics.

Realism fixes (P2):
  - Next-bar-open fills: signal uses the prior close; the trade is entered at the
    NEXT bar's open and exited at that bar's close (no same-bar lookahead).
  - Transaction costs: per round-trip slippage on both fills + brokerage/STT/
    exchange fees, market-aware (India .NS/.BO vs US).
  - Net-vs-gross reporting: gross (ideal fills) and net (after costs) so the cost
    drag on Sharpe/return is explicit.

Known limitation: SURVIVORSHIP BIAS is not corrected — only currently-listed
symbols with stored history are replayed; delisted names are absent. Treat
returns as optimistic. (Fixing needs a point-in-time / delisted universe.)
"""
import math
from dataclasses import dataclass
from datetime import date

from backend.decision.signals import compute_all_signals
from backend.decision.engine import make_recommendation


@dataclass(frozen=True)
class CostModel:
    """Round-trip transaction cost model in basis points (1 bp = 0.01%)."""
    slippage_bps: float = 5.0          # adverse price move per fill (each side)
    fee_bps_round_trip: float = 10.0   # brokerage + exchange + stamp + SEBI + GST
    stt_bps_round_trip: float = 20.0   # securities transaction tax

    @classmethod
    def for_symbol(cls, symbol: str) -> "CostModel":
        s = (symbol or "").upper()
        if s.endswith(".NS") or s.endswith(".BO"):
            # India cash/delivery equity: STT ~0.1% buy + 0.1% sell, thin spreads
            return cls(slippage_bps=5.0, fee_bps_round_trip=10.0, stt_bps_round_trip=20.0)
        # US equity: commission-free brokers; slippage + tiny regulatory fees
        return cls(slippage_bps=3.0, fee_bps_round_trip=1.0, stt_bps_round_trip=0.0)

    @property
    def slippage_fraction(self) -> float:
        return self.slippage_bps / 10000.0

    @property
    def fee_fraction(self) -> float:
        return (self.fee_bps_round_trip + self.stt_bps_round_trip) / 10000.0

    @property
    def per_side_cost_fraction(self) -> float:
        """Cost of a single fill: slippage + half the round-trip fees. Used by paper trading."""
        return self.slippage_fraction + self.fee_fraction / 2.0

    @property
    def round_trip_cost_fraction(self) -> float:
        """Full round-trip drag: slippage on both fills + the round-trip fees.
        Used to make the weight-tuning objective net-of-cost (R4.1)."""
        return 2.0 * self.slippage_fraction + self.fee_fraction

    def as_dict(self) -> dict:
        return {
            "slippage_bps": self.slippage_bps,
            "fee_bps_round_trip": self.fee_bps_round_trip,
            "stt_bps_round_trip": self.stt_bps_round_trip,
            "round_trip_fee_pct": round(self.fee_fraction, 6),
        }


@dataclass
class _DayResult:
    date: str
    close: float
    recommendation: str
    weighted_score: float
    gross_return: float | None   # ideal mid-price fill, no costs
    daily_return: float | None   # net of slippage + fees
    cumulative: float            # net cumulative


def _trade_returns(rec: str, entry_open: float, exit_close: float, cm: CostModel) -> tuple[float, float]:
    """Return (gross, net) for one round-trip trade. gross = mid fills; net = +slippage +fees."""
    slip = cm.slippage_fraction
    raw = (exit_close - entry_open) / entry_open
    if rec == "SELL":
        raw = -raw
        entry_eff = entry_open * (1 - slip)   # sell to open (receive less)
        exit_eff = exit_close * (1 + slip)    # buy to close (pay more)
        gross_eff = (entry_eff - exit_eff) / entry_eff
    else:  # BUY
        entry_eff = entry_open * (1 + slip)   # buy to open (pay more)
        exit_eff = exit_close * (1 - slip)    # sell to close (receive less)
        gross_eff = (exit_eff - entry_eff) / entry_eff
    net = gross_eff - cm.fee_fraction
    return raw, net


def run_backtest(
    analytics_rows: list,
    ohlcv_rows: list,
    sentiment_by_date: dict[date, float],
    cost_model: CostModel | None = None,
    hold_days: int = 1,
    capital: float | None = None,
    position_fraction: float = 1.0,
) -> dict:
    """Replay signals over historical data with realistic fills + costs.

    analytics_rows / ohlcv_rows: asyncpg Records ordered by timestamp asc.
    sentiment_by_date: {date: count-weighted score}.
    cost_model: per-symbol cost assumptions (defaults to a generic model).

    Two modes:
      - Default (hold_days=1, capital=None): the original daily-rebalanced replay —
        each day's signal is a fresh one-bar trade; returns are compounded as fractions.
      - Discrete (hold_days>1 or capital set, P2.2): non-overlapping multi-bar trades on a
        real capital base sized by `position_fraction` of equity, so capital/position
        constraints and a realistic holding period are respected.
    """
    if hold_days <= 1 and capital is None:
        return _run_daily(analytics_rows, ohlcv_rows, sentiment_by_date, cost_model)
    return _run_discrete(analytics_rows, ohlcv_rows, sentiment_by_date,
                         cost_model, max(1, hold_days), capital, position_fraction)


def _run_daily(
    analytics_rows: list,
    ohlcv_rows: list,
    sentiment_by_date: dict[date, float],
    cost_model: CostModel | None = None,
) -> dict:
    cm = cost_model or CostModel()

    def _to_date(ts):
        return ts.date() if hasattr(ts, "date") else ts

    close_by_date: dict[date, float] = {
        _to_date(r["timestamp"]): float(r["close"]) for r in ohlcv_rows
    }
    open_by_date: dict[date, float] = {
        _to_date(r["timestamp"]): float(r["open"])
        for r in ohlcv_rows if r.get("open") is not None
    }
    volume_by_date: dict[date, float] = {
        _to_date(r["timestamp"]): float(r["volume"])
        for r in ohlcv_rows if r.get("volume") is not None
    }
    analytics_by_date: dict[date, object] = {
        _to_date(r["timestamp"]): r for r in analytics_rows
    }

    # Precompute rolling 20-day avg volume keyed by date
    sorted_vol_dates = sorted(volume_by_date.keys())
    avg_volume_by_date: dict[date, float] = {}
    for i, d in enumerate(sorted_vol_dates):
        window = [volume_by_date[sorted_vol_dates[j]] for j in range(max(0, i - 19), i + 1)]
        avg_volume_by_date[d] = sum(window) / len(window) if window else 0

    sorted_dates = sorted(close_by_date.keys())
    sorted_sent_dates = sorted(sentiment_by_date.keys())

    def _f(v):
        return float(v) if v is not None else None

    def _nearest_sentiment(d: date) -> float | None:
        for sd in reversed(sorted_sent_dates):
            if sd <= d:
                return sentiment_by_date[sd]
        return None

    day_results: list[_DayResult] = []
    cumulative = 1.0          # net
    gross_cumulative = 1.0
    peak = 1.0
    max_drawdown = 0.0
    net_returns: list[float] = []
    trades = wins = 0

    for i, d in enumerate(sorted_dates[:-1]):
        analytics = analytics_by_date.get(d)
        if analytics is None:
            continue

        close = close_by_date.get(d)            # signal-day close (drives signals)
        next_d = sorted_dates[i + 1]
        entry_open = open_by_date.get(next_d, close_by_date.get(next_d))  # next bar open (fallback close)
        exit_close = close_by_date.get(next_d)
        if close is None or entry_open is None or exit_close is None or entry_open == 0:
            continue

        vol_ratio = None
        avg_vol = avg_volume_by_date.get(d, 0)
        if avg_vol > 0 and d in volume_by_date:
            vol_ratio = volume_by_date[d] / avg_vol

        signals = compute_all_signals(
            close=close,
            rsi=_f(analytics["rsi_14"]),
            sma_20=_f(analytics["sma_20"]),
            momentum_10=_f(analytics["momentum_10"]),
            vol_20=_f(analytics["volatility_20"]),
            sentiment_score=_nearest_sentiment(d),
            predicted_close=None,  # no historical forecasts stored
            ema_9=_f(analytics["ema_9"]) if "ema_9" in analytics.keys() else None,
            ema_20=_f(analytics["ema_20"]),
            volume_ratio=vol_ratio,
        )
        result = make_recommendation(signals, _f(analytics["volatility_20"]))
        rec = result["recommendation"]

        gross_ret = net_ret = None
        if rec in ("BUY", "SELL"):
            gross_ret, net_ret = _trade_returns(rec, entry_open, exit_close, cm)
            cumulative *= 1 + net_ret
            gross_cumulative *= 1 + gross_ret
            net_returns.append(net_ret)
            trades += 1
            if net_ret > 0:
                wins += 1

        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak
        if dd > max_drawdown:
            max_drawdown = dd

        day_results.append(_DayResult(
            date=str(d),
            close=close,
            recommendation=rec,
            weighted_score=round(result["weighted_score"], 4),
            gross_return=round(gross_ret, 6) if gross_ret is not None else None,
            daily_return=round(net_ret, 6) if net_ret is not None else None,
            cumulative=round(cumulative, 6),
        ))

    sharpe = None
    if len(net_returns) >= 5:
        mean_r = sum(net_returns) / len(net_returns)
        var = sum((r - mean_r) ** 2 for r in net_returns) / len(net_returns)
        std_r = math.sqrt(var)
        if std_r > 0:
            sharpe = round((mean_r / std_r) * math.sqrt(252), 4)

    net_total = cumulative - 1.0
    gross_total = gross_cumulative - 1.0

    return {
        "days_analyzed": len(day_results),
        "trades": trades,
        "win_rate": round(wins / trades, 4) if trades > 0 else None,
        "total_return": round(net_total, 6),          # net of costs (headline)
        "gross_return": round(gross_total, 6),         # ideal fills, no costs
        "cost_drag": round(gross_total - net_total, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe_ratio": sharpe,                        # net-of-cost Sharpe
        "cost_model": cm.as_dict(),
        "assumptions": [
            "Entry at next bar's open, exit at that bar's close — signal uses the prior close (no lookahead).",
            "Costs per round-trip: slippage on both fills + brokerage/STT/exchange fees (market-aware).",
            "SURVIVORSHIP BIAS NOT corrected — only listed symbols with stored history are replayed; "
            "delisted names are absent, so returns are optimistic.",
            "Single symbol, one-bar holding period; no position sizing or capital constraints.",
        ],
        "equity_curve": [
            {"date": r.date, "cumulative": r.cumulative}
            for r in day_results
        ],
        "daily": [
            {
                "date": r.date,
                "close": r.close,
                "recommendation": r.recommendation,
                "weighted_score": r.weighted_score,
                "gross_return": r.gross_return,
                "daily_return": r.daily_return,
            }
            for r in day_results
        ],
    }


def _run_discrete(
    analytics_rows: list,
    ohlcv_rows: list,
    sentiment_by_date: dict[date, float],
    cost_model: CostModel | None,
    hold_days: int,
    capital: float | None,
    position_fraction: float,
) -> dict:
    """Non-overlapping multi-bar trades on a real capital base (P2.2).

    A signal opens a position at the next bar's open and closes it `hold_days` bars later
    at the close. While a position is open, later signals are ignored (no overlap / no
    pyramiding). Each trade risks `position_fraction` of current equity; P&L compounds on
    the capital base, so position and capital constraints are honoured.
    """
    cm = cost_model or CostModel()
    capital = float(capital) if capital is not None else 100_000.0
    position_fraction = max(0.0, min(position_fraction, 1.0)) or 1.0

    def _to_date(ts):
        return ts.date() if hasattr(ts, "date") else ts

    def _f(v):
        return float(v) if v is not None else None

    close_by_date = {_to_date(r["timestamp"]): float(r["close"]) for r in ohlcv_rows}
    open_by_date = {_to_date(r["timestamp"]): float(r["open"])
                    for r in ohlcv_rows if r.get("open") is not None}
    volume_by_date = {_to_date(r["timestamp"]): float(r["volume"])
                      for r in ohlcv_rows if r.get("volume") is not None}
    analytics_by_date = {_to_date(r["timestamp"]): r for r in analytics_rows}

    sorted_vol_dates = sorted(volume_by_date.keys())
    avg_volume_by_date: dict[date, float] = {}
    for i, d in enumerate(sorted_vol_dates):
        window = [volume_by_date[sorted_vol_dates[j]] for j in range(max(0, i - 19), i + 1)]
        avg_volume_by_date[d] = sum(window) / len(window) if window else 0

    sorted_dates = sorted(close_by_date.keys())
    sorted_sent_dates = sorted(sentiment_by_date.keys())

    def _nearest_sentiment(d: date):
        for sd in reversed(sorted_sent_dates):
            if sd <= d:
                return sentiment_by_date[sd]
        return None

    equity = capital
    starting = capital
    trades_log: list[dict] = []
    equity_curve = [{"date": str(sorted_dates[0]), "equity": round(equity, 2)}] if sorted_dates else []
    trade_returns: list[float] = []
    wins = 0
    peak = equity
    max_dd = 0.0

    n = len(sorted_dates)
    i = 0
    while i < n - 1:
        d = sorted_dates[i]
        analytics = analytics_by_date.get(d)
        if analytics is None:
            i += 1
            continue

        exit_idx = i + hold_days
        if exit_idx >= n:
            break

        entry_d = sorted_dates[i + 1]
        exit_d = sorted_dates[exit_idx]
        entry_open = open_by_date.get(entry_d, close_by_date.get(entry_d))
        exit_close = close_by_date.get(exit_d)
        close = close_by_date.get(d)
        if close is None or entry_open is None or exit_close is None or entry_open == 0:
            i += 1
            continue

        vol_ratio = None
        avg_vol = avg_volume_by_date.get(d, 0)
        if avg_vol > 0 and d in volume_by_date:
            vol_ratio = volume_by_date[d] / avg_vol

        signals = compute_all_signals(
            close=close, rsi=_f(analytics["rsi_14"]), sma_20=_f(analytics["sma_20"]),
            momentum_10=_f(analytics["momentum_10"]), vol_20=_f(analytics["volatility_20"]),
            sentiment_score=_nearest_sentiment(d), predicted_close=None,
            ema_9=_f(analytics["ema_9"]) if "ema_9" in analytics.keys() else None,
            ema_20=_f(analytics["ema_20"]), volume_ratio=vol_ratio,
        )
        result = make_recommendation(signals, _f(analytics["volatility_20"]))
        rec = result["recommendation"]

        if rec not in ("BUY", "SELL"):
            i += 1
            continue

        _, net_ret = _trade_returns(rec, entry_open, exit_close, cm)
        position_value = position_fraction * equity
        pnl = position_value * net_ret
        equity += pnl
        trade_returns.append(net_ret)
        if net_ret > 0:
            wins += 1
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0.0
        max_dd = max(max_dd, dd)

        trades_log.append({
            "entry_date": str(entry_d), "exit_date": str(exit_d), "recommendation": rec,
            "entry_price": round(entry_open, 4), "exit_price": round(exit_close, 4),
            "net_return": round(net_ret, 6), "pnl": round(pnl, 2),
            "equity": round(equity, 2),
        })
        equity_curve.append({"date": str(exit_d), "equity": round(equity, 2)})

        i = exit_idx  # non-overlapping: next signal evaluated only after this trade closes

    sharpe = None
    if len(trade_returns) >= 5:
        mean_r = sum(trade_returns) / len(trade_returns)
        var = sum((r - mean_r) ** 2 for r in trade_returns) / len(trade_returns)
        sd = var ** 0.5
        if sd > 0:
            sharpe = round((mean_r / sd) * math.sqrt(252 / hold_days), 4)

    trades = len(trade_returns)
    return {
        "mode": "discrete",
        "hold_days": hold_days,
        "position_fraction": position_fraction,
        "starting_capital": round(starting, 2),
        "ending_equity": round(equity, 2),
        "trades": trades,
        "win_rate": round(wins / trades, 4) if trades else None,
        "total_return": round(equity / starting - 1.0, 6) if starting else None,
        "max_drawdown": round(max_dd, 6),
        "sharpe_ratio": sharpe,
        "cost_model": cm.as_dict(),
        "assumptions": [
            f"Non-overlapping trades held {hold_days} bar(s): enter next-bar open, exit close "
            f"{hold_days} bar(s) later (no lookahead, no pyramiding).",
            f"Each trade risks {position_fraction:.0%} of current equity; P&L compounds on capital.",
            "Costs per round-trip: slippage on both fills + brokerage/STT/exchange fees (market-aware).",
            "SURVIVORSHIP BIAS NOT corrected — only listed symbols with stored history are replayed; "
            "delisted names are absent, so returns are optimistic.",
        ],
        "equity_curve": equity_curve,
        "trades_log": trades_log,
    }
