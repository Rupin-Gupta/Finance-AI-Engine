"""P14: ML directional model — shallow gradient-boosted trees, walk-forward validated.

HistGradientBoostingClassifier: handles NaN natively, needs no scaling (tree model),
fast on 100k+ rows. Kept shallow + regularized because financial data is low
signal-to-noise — depth invites overfitting. Validation is walk-forward (TimeSeriesSplit):
every test fold is strictly after its train fold, so there is no lookahead and the
reported edge is the only one we trust. The job promotes a model ONLY if its
out-of-sample edge clears the gate; otherwise the signal is never used.
"""
import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# Promotion gate — modest OOS edge required before the signal goes live.
PROMOTE_MIN_AUC = 0.53
PROMOTE_MIN_HIT_RATE = 0.51

_RANDOM_STATE = 42


@dataclass
class ModelMetrics:
    n_samples: int = 0
    n_features: int = 0
    oos_auc: float | None = None
    oos_hit_rate: float | None = None
    oos_brier: float | None = None
    folds: int = 0

    def passes_gate(self) -> bool:
        return (self.oos_auc is not None and self.oos_hit_rate is not None
                and self.oos_auc >= PROMOTE_MIN_AUC
                and self.oos_hit_rate >= PROMOTE_MIN_HIT_RATE)


@dataclass
class ModelBundle:
    estimator: object
    feature_names: list[str]
    horizon: int
    threshold: float
    metrics: ModelMetrics = field(default_factory=ModelMetrics)


def _new_estimator():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=200,
        l2_regularization=1.0, min_samples_leaf=50, random_state=_RANDOM_STATE,
    )


def walk_forward_metrics(X: list[list], y: list[int], n_splits: int = 4) -> ModelMetrics:
    """Out-of-sample metrics via TimeSeriesSplit (rows must be time-ordered)."""
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, brier_score_loss

    Xa, ya = np.asarray(X, dtype=float), np.asarray(y, dtype=int)
    m = ModelMetrics(n_samples=len(ya), n_features=Xa.shape[1] if Xa.size else 0)
    if len(ya) < 200 or len(set(ya.tolist())) < 2:
        return m  # too little data / single class → no trustworthy edge

    oos_p, oos_y = [], []
    splits = TimeSeriesSplit(n_splits=min(n_splits, max(2, len(ya) // 200)))
    for tr, te in splits.split(Xa):
        if len(set(ya[tr].tolist())) < 2:
            continue
        est = _new_estimator()
        est.fit(Xa[tr], ya[tr])
        oos_p.extend(est.predict_proba(Xa[te])[:, 1].tolist())
        oos_y.extend(ya[te].tolist())
        m.folds += 1

    if len(set(oos_y)) >= 2:
        p = np.asarray(oos_p)
        yt = np.asarray(oos_y)
        m.oos_auc = round(float(roc_auc_score(yt, p)), 4)
        m.oos_hit_rate = round(float(((p > 0.5).astype(int) == yt).mean()), 4)
        m.oos_brier = round(float(brier_score_loss(yt, p)), 4)
    return m


def train_bundle(X: list[list], y: list[int], feature_names: list[str],
                 horizon: int, threshold: float) -> ModelBundle:
    """Walk-forward evaluate, then fit the final model on ALL data for deployment."""
    metrics = walk_forward_metrics(X, y)
    est = _new_estimator()
    est.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
    return ModelBundle(est, feature_names, horizon, threshold, metrics)


def predict_proba(bundle: ModelBundle, feature_vec: list) -> float | None:
    """P(up) for one feature row, or None on any failure (graceful)."""
    try:
        import numpy as _np
        arr = _np.asarray([feature_vec], dtype=float)
        return round(float(bundle.estimator.predict_proba(arr)[0, 1]), 4)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML predict failed: %s", exc)
        return None


def save_bundle(bundle: ModelBundle, path: str) -> None:
    import joblib
    joblib.dump(bundle, path)


def load_bundle(path: str) -> ModelBundle | None:
    import joblib
    try:
        return joblib.load(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML model load failed (%s): %s", path, exc)
        return None
