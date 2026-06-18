"""Dynamic weight tuning (R4): evaluate / optimize / walk-forward + engine override."""
import pytest

from backend.analytics.weight_tuning import (
    evaluate_weights, optimize_weights, walk_forward,
    walk_forward_expanding, attribution_prior,
)
from backend.decision.signals import compute_all_signals, SIGNAL_WEIGHTS
from backend.db.queries import signal_weights as sw_q


def _row(score, move):
    return {"signals": {"rsi": {"score": score, "weight": 0.12}}, "realized_move": move}


# ---------------------------------------------------------------------------
# evaluate_weights
# ---------------------------------------------------------------------------

def test_evaluate_weights_labels_and_scores():
    rows = [_row(1.0, 0.05), _row(-1.0, -0.04)]
    res = evaluate_weights(rows, {"rsi": 1.0}, threshold=0.3)
    assert res["trades"] == 2
    assert res["hit_rate"] == 1.0          # BUY into +move, SELL into -move
    assert res["avg_return"] == 0.045


def test_evaluate_weights_below_threshold_holds():
    rows = [_row(1.0, 0.05)]
    res = evaluate_weights(rows, {"rsi": 0.12}, threshold=0.3)  # 0.12 < 0.3 → HOLD
    assert res["trades"] == 0


# ---------------------------------------------------------------------------
# optimize_weights
# ---------------------------------------------------------------------------

def test_optimize_beats_base_when_base_underweights_the_edge():
    # rsi-only edge; default rsi weight (0.12) < threshold → base never trades (0 return).
    rows = [_row(1.0, 0.03) for _ in range(12)]
    res = optimize_weights(rows, threshold=0.3, min_trades=10, seed=0)
    assert abs(sum(res["weights"].values()) - 1.0) < 1e-3     # stays on the simplex
    assert res["metric"]["avg_return"] >= 0.0                 # never worse than base
    assert res["metric"]["avg_return"] > 0.0                  # found the rsi-heavy edge


# ---------------------------------------------------------------------------
# walk_forward
# ---------------------------------------------------------------------------

def test_walk_forward_reports_out_of_sample():
    rows = [_row(1.0, 0.03) for _ in range(20)]
    res = walk_forward(rows, threshold=0.3, min_trades=10, seed=0)
    assert abs(sum(res["weights"].values()) - 1.0) < 1e-3
    assert "improvement" in res and "out_of_sample" in res
    assert res["n_train"] + res["n_test"] == 20


def test_walk_forward_insufficient_history():
    res = walk_forward([_row(1.0, 0.03) for _ in range(5)], threshold=0.3)
    assert res["promotable"] is False


# ---------------------------------------------------------------------------
# R4 upgrades: net-of-cost objective, attribution prior, expanding CV
# ---------------------------------------------------------------------------

def test_evaluate_weights_net_of_cost_subtracts_cost():
    rows = [{"signals": {"rsi": {"score": 1.0, "weight": 0.12}},
             "realized_move": 0.05, "cost_fraction": 0.02}]
    gross = evaluate_weights(rows, {"rsi": 1.0}, threshold=0.3)
    net = evaluate_weights(rows, {"rsi": 1.0}, threshold=0.3, use_costs=True)
    assert gross["avg_return"] == 0.05            # unchanged default behaviour
    assert net["net_return"] == round(0.05 - 0.02, 6)


def test_attribution_prior_favors_positive_contributors():
    contrib = [{"signal": "rsi", "attributed_return": 0.10},
               {"signal": "trend", "attributed_return": -0.05}]
    prior = attribution_prior(contrib)
    assert abs(sum(prior.values()) - 1.0) < 1e-3
    assert set(prior) == set(SIGNAL_WEIGHTS)       # all signals present
    assert prior["rsi"] > prior["trend"]           # winner gets more weight


def test_walk_forward_expanding_runs_folds_and_stays_on_simplex():
    rows = [_row(1.0, 0.03) for _ in range(40)]
    res = walk_forward_expanding(rows, threshold=0.3, k=3, min_trades=5, seed=0)
    assert res["method"] == "expanding"
    assert len(res["folds"]) >= 1
    assert "mean_improvement" in res
    assert abs(sum(res["weights"].values()) - 1.0) < 1e-3


def test_walk_forward_expanding_falls_back_to_holdout_when_short():
    res = walk_forward_expanding([_row(1.0, 0.03) for _ in range(20)],
                                 threshold=0.3, k=4, min_trades=10, seed=0)
    assert res["method"] == "holdout"


# ---------------------------------------------------------------------------
# engine override
# ---------------------------------------------------------------------------

def test_compute_all_signals_applies_weight_override():
    sigs = compute_all_signals(
        close=100, rsi=20, sma_20=90, momentum_10=0.06, vol_20=0.10,
        sentiment_score=None, predicted_close=None, ema_9=100, ema_20=95,
        volume_ratio=1.0, weights={"rsi": 0.99},
    )
    by = {s.name: s.weight for s in sigs}
    assert by["rsi"] == 0.99                          # overridden
    assert by["trend"] == SIGNAL_WEIGHTS["trend"]     # untouched


def test_compute_all_signals_default_weights_unchanged():
    sigs = compute_all_signals(
        close=100, rsi=20, sma_20=90, momentum_10=0.06, vol_20=0.10,
        sentiment_score=None, predicted_close=None, ema_9=100, ema_20=95, volume_ratio=1.0,
    )
    assert {s.name: s.weight for s in sigs}["rsi"] == SIGNAL_WEIGHTS["rsi"]


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------

class FakeConn:
    def __init__(self, row=None):
        self._row = row
        self.calls = []

    async def fetchrow(self, q, *a):
        self.calls.append(q)
        return self._row

    async def execute(self, q, *a):
        self.calls.append(q)

    async def fetch(self, q, *a):
        return []


@pytest.mark.asyncio
async def test_get_active_weights_none_when_empty():
    assert await sw_q.get_active_weights(FakeConn(row=None)) is None


@pytest.mark.asyncio
async def test_get_active_weights_parses_json_string():
    out = await sw_q.get_active_weights(FakeConn(row={"weights_json": '{"rsi": 0.3}'}))
    assert out == {"rsi": 0.3}
