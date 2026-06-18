"""P14 ML directional signal: no-lookahead features, walk-forward metrics, gate, scorer."""
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.ml.features import build_dataset, build_feature_vector, FEATURE_NAMES
from backend.ml.model import (
    ModelMetrics, predict_proba, train_bundle, walk_forward_metrics,
)
from backend.decision.signals import score_ml, compute_all_signals, ML_SIGNAL_WEIGHT


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------

def test_feature_vector_order_and_ratios():
    vec = build_feature_vector(rsi=55, sma_20=100, close=103, momentum=0.02,
                               volatility=0.3, ema_9=101, ema_20=100, sentiment=0.2)
    assert len(vec) == len(FEATURE_NAMES)
    assert vec[0] == 55.0                       # rsi
    assert vec[1] == pytest.approx(0.03)        # trend_dev (103-100)/100
    assert vec[4] == pytest.approx(0.01)        # ema_gap (101-100)/100
    assert vec[5] == 0.2                        # sentiment


def test_feature_vector_missing_sentiment_defaults_zero():
    vec = build_feature_vector(50, 100, 100, 0.0, 0.2, 100, 100, None)
    assert vec[5] == 0.0


def _arows(closes, start=date(2025, 1, 1)):
    rows = []
    for i, c in enumerate(closes):
        rows.append({"timestamp": datetime(start.year, start.month, start.day) + timedelta(days=i),
                     "rsi_14": 50, "sma_20": c, "momentum_10": 0.0,
                     "volatility_20": 0.3, "ema_9": c, "ema_20": c})
    return rows


def test_build_dataset_labels_use_future_no_lookahead():
    closes = [100, 101, 102, 103, 104, 110]   # index5 is +5d from index0
    start = date(2025, 1, 1)
    arows = _arows(closes, start)
    cbd = {start + timedelta(days=i): c for i, c in enumerate(closes)}
    X, y, dates = build_dataset(arows, cbd, {}, horizon=5, threshold=0.0)
    # only rows whose +5d close exists get labelled → row0 labelled (100→110 up=1)
    assert len(X) == len(y) == len(dates)
    assert y[0] == 1
    # last rows (no future bar 5d ahead) are excluded, never guessed
    assert dates[0] == start
    assert max(dates) < start + timedelta(days=5)


def test_build_dataset_skips_rows_without_close():
    arows = _arows([100, 101, 102, 103, 104, 90])
    cbd = {}  # no closes at all
    X, y, _ = build_dataset(arows, cbd, {}, horizon=5)
    assert X == [] and y == []


# ---------------------------------------------------------------------------
# model: walk-forward + gate
# ---------------------------------------------------------------------------

def _separable(n=600):
    """Feature 0 strongly predicts the label → AUC should be high OOS."""
    import random
    random.seed(1)
    X, y = [], []
    for _ in range(n):
        label = random.randint(0, 1)
        signal = (label - 0.5) * 2 + random.gauss(0, 0.4)   # informative
        X.append([signal, random.gauss(0, 1), random.gauss(0, 1),
                  random.gauss(0, 1), random.gauss(0, 1), 0.0])
        y.append(label)
    return X, y


def test_walk_forward_metrics_detects_signal():
    X, y = _separable()
    m = walk_forward_metrics(X, y, n_splits=4)
    assert m.folds >= 2
    assert m.oos_auc is not None and m.oos_auc > 0.7
    assert m.passes_gate() is True


def test_walk_forward_metrics_insufficient_data():
    m = walk_forward_metrics([[1, 2, 3, 4, 5, 0]] * 10, [0] * 10)
    assert m.oos_auc is None
    assert m.passes_gate() is False


def test_gate_rejects_no_edge():
    m = ModelMetrics(oos_auc=0.50, oos_hit_rate=0.49)
    assert m.passes_gate() is False
    assert ModelMetrics(oos_auc=0.55, oos_hit_rate=0.53).passes_gate() is True


def test_train_bundle_predicts_in_range():
    X, y = _separable()
    bundle = train_bundle(X, y, FEATURE_NAMES, horizon=5, threshold=0.0)
    p = predict_proba(bundle, [2.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert 0.0 <= p <= 1.0
    assert bundle.feature_names == FEATURE_NAMES


def test_predict_proba_handles_bad_input():
    X, y = _separable()
    bundle = train_bundle(X, y, FEATURE_NAMES, 5, 0.0)
    assert predict_proba(bundle, [None] * 6) is not None  # HGB handles NaN → still a prob


# ---------------------------------------------------------------------------
# signal scorer + engine append
# ---------------------------------------------------------------------------

def test_score_ml_levels():
    assert score_ml(0.70).score == 1.0
    assert score_ml(0.58).score == 0.5
    assert score_ml(0.50).score == 0.0
    assert score_ml(0.40).score == -0.5
    assert score_ml(0.30).score == -1.0
    assert score_ml(None).score == 0.0
    assert score_ml(0.70).weight == ML_SIGNAL_WEIGHT


def test_compute_all_signals_appends_ml_only_when_prob_given():
    base = compute_all_signals(100, 50, 99, 0.0, 0.3, 0.1, 101)
    assert not any(s.name == "ml" for s in base)
    withml = compute_all_signals(100, 50, 99, 0.0, 0.3, 0.1, 101, ml_prob=0.7)
    ml = [s for s in withml if s.name == "ml"]
    assert len(ml) == 1 and ml[0].score == 1.0
