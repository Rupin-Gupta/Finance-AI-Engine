"""P14 inference: load the active promoted model (cached) and predict P(up) per symbol.

Guarded everywhere — a missing/corrupt model or a predict failure returns None, so the
decision path simply omits the ML overlay (zero behaviour change vs pre-P14).
"""
import logging

from backend.db.queries.ml_models import get_active_model
from backend.ml.features import build_feature_vector
from backend.ml.model import load_bundle, predict_proba

logger = logging.getLogger(__name__)

# version -> ModelBundle (process-local; a newer promoted version loads on first use).
_BUNDLE_CACHE: dict[str, object] = {}


async def get_active_bundle(conn):
    row = await get_active_model(conn)
    if not row:
        return None
    version = row["version"]
    if version not in _BUNDLE_CACHE:
        bundle = load_bundle(row["path"])
        if bundle is None:
            return None
        _BUNDLE_CACHE[version] = bundle
    return _BUNDLE_CACHE[version]


async def predict_symbol_prob(conn, latest_analytics, close, sentiment_score) -> float | None:
    """P(up) for a symbol from its latest analytics row + close + sentiment. None if no model."""
    if latest_analytics is None or close is None:
        return None
    bundle = await get_active_bundle(conn)
    if bundle is None:
        return None
    vec = build_feature_vector(
        latest_analytics.get("rsi_14"), latest_analytics.get("sma_20"), close,
        latest_analytics.get("momentum_10"), latest_analytics.get("volatility_20"),
        latest_analytics.get("ema_9"), latest_analytics.get("ema_20"), sentiment_score,
    )
    return predict_proba(bundle, vec)
