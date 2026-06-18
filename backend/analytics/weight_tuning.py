"""Dynamic signal-weight optimization (R4) — pure, no I/O.

Re-weights the 8 signals against realized outcomes and searches for a weight vector
that would have made more money, then validates it **out-of-sample** (walk-forward /
expanding-window CV) so we don't overfit. The objective (relabel BUY/SELL/HOLD via a
threshold on the re-weighted score) is non-smooth, so we use a constrained
random-simplex search rather than a gradient optimizer.

R4 upgrades:
  - net-of-cost objective: subtract each trade's round-trip cost (`cost_fraction`),
    or optimize the per-trade Sharpe instead of raw average return.
  - attribution prior: seed the search around an R3 signal-attribution weight vector.
  - expanding-window CV: validate across several sequential folds, not one split.

Scored rows (chronological) must carry: signals {name:{score,...}} and realized_move.
Optional per row: cost_fraction (round-trip cost) for net-of-cost scoring.
"""
import numpy as np

from backend.decision.signals import SIGNAL_WEIGHTS

SIGNAL_NAMES = list(SIGNAL_WEIGHTS.keys())

_OBJECTIVE_KEY = {"avg_return": "avg_return", "net_return": "net_return", "sharpe": "sharpe"}


def _metric_key(objective: str) -> str:
    return _OBJECTIVE_KEY.get(objective, "avg_return")


def evaluate_weights(
    scored: list[dict],
    weights: dict,
    threshold: float,
    *,
    use_costs: bool = False,
    objective: str = "avg_return",
) -> dict:
    """Relabel each decision with `weights` and score it against the realized move.

    use_costs=True subtracts each trade's round-trip `cost_fraction` (net-of-cost, R4.1).
    Returns trades / hit_rate / avg_return / net_return / sharpe. With use_costs=False,
    net_return == avg_return (the original gross behaviour, unchanged).
    """
    trades = hits = 0
    total = 0.0
    trade_rets: list[float] = []
    for r in scored:
        sigs = r.get("signals") or {}
        w = sum((sigs.get(name, {}).get("score") or 0.0) * wt for name, wt in weights.items())
        move = r["realized_move"]
        if w >= threshold:
            rec, strat = "BUY", move
        elif w <= -threshold:
            rec, strat = "SELL", -move
        else:
            rec, strat = "HOLD", 0.0
        if rec == "HOLD":
            continue
        trades += 1
        cost = (r.get("cost_fraction") or 0.0) if use_costs else 0.0
        net = strat - cost
        trade_rets.append(net)
        total += net
        if (rec == "BUY" and move > 0) or (rec == "SELL" and move < 0):
            hits += 1

    n = len(scored)
    sharpe = None
    if len(trade_rets) >= 2:
        mean = sum(trade_rets) / len(trade_rets)
        var = sum((x - mean) ** 2 for x in trade_rets) / len(trade_rets)
        sd = var ** 0.5
        sharpe = round(mean / sd, 4) if sd > 0 else None

    avg = round(total / n, 6) if n else None
    return {
        "trades": trades,
        "hit_rate": round(hits / trades, 4) if trades else None,
        "avg_return": avg,
        "net_return": avg,
        "sharpe": sharpe,
    }


def attribution_prior(
    contribution: list[dict],
    base_weights: dict | None = None,
    floor: float = 0.005,
    blend: float = 0.5,
) -> dict:
    """Turn R3 signal attribution into a prior weight vector for the optimizer (R3→R4).

    Signals that earned more realized return get more prior weight; negative / absent
    contributors fall to `floor` (never fully zeroed). Blended with the base weights so
    signals with no attribution history retain their default. Returns a normalized dict
    over the base signal set.
    """
    base = base_weights or dict(SIGNAL_WEIGHTS)
    contrib = {c["signal"]: (c.get("attributed_return") or 0.0) for c in (contribution or [])}
    raw = {name: max(contrib.get(name, 0.0), 0.0) + floor for name in base}
    s = sum(raw.values())
    if s <= 0:
        return dict(base)
    attr_w = {k: v / s for k, v in raw.items()}
    mixed = {k: blend * attr_w[k] + (1 - blend) * base.get(k, 0.0) for k in base}
    t = sum(mixed.values())
    return {k: round(v / t, 4) for k, v in mixed.items()} if t > 0 else dict(base)


def optimize_weights(
    scored: list[dict],
    threshold: float,
    base_weights: dict | None = None,
    n_samples: int = 500,
    min_trades: int = 10,
    seed: int = 0,
    *,
    prior: dict | None = None,
    use_costs: bool = False,
    objective: str = "avg_return",
) -> dict:
    """Random-simplex search maximizing the chosen objective. Base weights are always a
    candidate, so the result never scores worse in-sample than the current weights. A
    `prior` (e.g. attribution-seeded) is added as a candidate and densely sampled around."""
    base = base_weights or dict(SIGNAL_WEIGHTS)
    names = list(base.keys())
    key = _metric_key(objective)

    def metric_of(res: dict) -> float:
        v = res.get(key)
        return v if v is not None else float("-inf")

    best_w = dict(base)
    best = evaluate_weights(scored, base, threshold, use_costs=use_costs, objective=objective)
    best_metric = metric_of(best)

    rng = np.random.default_rng(seed)
    candidate_vecs: list[np.ndarray] = []
    if prior:
        candidate_vecs.append(np.array([float(prior.get(n, base.get(n, 0.0))) for n in names]))

    samples = list(rng.dirichlet(np.ones(len(names)), size=n_samples))
    if prior:  # focused exploration centred on the prior
        alpha = np.array([max(prior.get(n, 0.0), 1e-3) for n in names]) * 50.0
        samples += list(rng.dirichlet(alpha, size=max(1, n_samples // 2)))

    for vec in candidate_vecs + samples:
        cand = {name: float(w) for name, w in zip(names, vec)}
        res = evaluate_weights(scored, cand, threshold, use_costs=use_costs, objective=objective)
        if res["trades"] < min_trades or metric_of(res) == float("-inf"):
            continue
        if metric_of(res) > best_metric:
            best_metric, best_w, best = metric_of(res), cand, res

    return {"weights": {k: round(v, 4) for k, v in best_w.items()}, "metric": best}


def walk_forward(
    scored: list[dict],
    threshold: float,
    base_weights: dict | None = None,
    train_frac: float = 0.7,
    *,
    use_costs: bool = False,
    objective: str = "avg_return",
    prior: dict | None = None,
    **opt_kwargs,
) -> dict:
    """Optimize on the earlier `train_frac` of decisions, evaluate on the held-out tail.

    Reports the optimized weights' out-of-sample return vs the base weights' — the only
    honest basis for promoting new weights. `scored` must be chronological.
    """
    base = base_weights or dict(SIGNAL_WEIGHTS)
    n = len(scored)
    split = int(n * train_frac)
    train, test = scored[:split], scored[split:]
    if len(train) < 10 or len(test) < 5:
        return {"weights": dict(base), "promotable": False, "reason": "insufficient history",
                "n_train": len(train), "n_test": len(test)}

    opt = optimize_weights(train, threshold, base_weights=base, prior=prior,
                           use_costs=use_costs, objective=objective, **opt_kwargs)
    oos = evaluate_weights(test, opt["weights"], threshold, use_costs=use_costs, objective=objective)
    base_oos = evaluate_weights(test, base, threshold, use_costs=use_costs, objective=objective)

    key = _metric_key(objective)
    improvement = round((oos[key] or 0.0) - (base_oos[key] or 0.0), 6)
    return {
        "weights": opt["weights"],
        "in_sample": opt["metric"],
        "out_of_sample": oos,
        "base_out_of_sample": base_oos,
        "improvement": improvement,
        # normalized scalars (the chosen objective) for objective-agnostic persistence
        "in_sample_metric": opt["metric"].get(key),
        "oos_metric": oos.get(key),
        "base_oos_metric": base_oos.get(key),
        "promotable": improvement > 0 and oos["trades"] >= 5,
        "objective": objective,
        "method": "holdout",
        "n_train": len(train),
        "n_test": len(test),
    }


def walk_forward_expanding(
    scored: list[dict],
    threshold: float,
    base_weights: dict | None = None,
    k: int = 4,
    min_train: int = 10,
    min_test: int = 5,
    *,
    use_costs: bool = False,
    objective: str = "avg_return",
    prior: dict | None = None,
    **opt_kwargs,
) -> dict:
    """Expanding-window cross-validation (R4.2): k sequential folds, each trained on all
    prior data and tested on the next slice. More robust than one 70/30 split — every
    late-period regime is validated out-of-sample. Promotes only if the MEAN OOS
    improvement across folds is positive; the deployed weights are optimized on the full
    history. Falls back to a single holdout when history is too short for k folds.
    """
    base = base_weights or dict(SIGNAL_WEIGHTS)
    n = len(scored)
    key = _metric_key(objective)

    if n < min_train + k * min_test:
        wf = walk_forward(scored, threshold, base_weights=base, use_costs=use_costs,
                          objective=objective, prior=prior, **opt_kwargs)
        wf["folds"] = []
        wf["mean_improvement"] = wf.get("improvement")
        wf["method"] = "holdout"
        return wf

    test_size = (n - min_train) // k
    folds: list[dict] = []
    improvements: list[float] = []
    oos_vals: list[float] = []
    base_vals: list[float] = []
    total_oos_trades = 0

    for i in range(k):
        train_end = min_train + i * test_size
        test_end = n if i == k - 1 else train_end + test_size
        train, test = scored[:train_end], scored[train_end:test_end]
        if len(train) < min_train or len(test) < min_test:
            continue
        opt = optimize_weights(train, threshold, base_weights=base, prior=prior,
                               use_costs=use_costs, objective=objective, **opt_kwargs)
        oos = evaluate_weights(test, opt["weights"], threshold, use_costs=use_costs, objective=objective)
        base_oos = evaluate_weights(test, base, threshold, use_costs=use_costs, objective=objective)
        imp = round((oos[key] or 0.0) - (base_oos[key] or 0.0), 6)
        improvements.append(imp)
        oos_vals.append(oos[key] or 0.0)
        base_vals.append(base_oos[key] or 0.0)
        total_oos_trades += oos["trades"]
        folds.append({"fold": i + 1, "n_train": len(train), "n_test": len(test),
                      "improvement": imp, "out_of_sample": oos, "base_out_of_sample": base_oos})

    mean_imp = round(sum(improvements) / len(improvements), 6) if improvements else None
    full = optimize_weights(scored, threshold, base_weights=base, prior=prior,
                            use_costs=use_costs, objective=objective, **opt_kwargs)
    promotable = bool(improvements) and mean_imp is not None and mean_imp > 0 and total_oos_trades >= 5
    oos_mean = round(sum(oos_vals) / len(oos_vals), 6) if oos_vals else None
    base_mean = round(sum(base_vals) / len(base_vals), 6) if base_vals else None

    return {
        "weights": full["weights"],
        "in_sample": full["metric"],
        "folds": folds,
        "mean_improvement": mean_imp,
        "improvement": mean_imp,
        "out_of_sample": {key: oos_mean, "trades": total_oos_trades},
        "base_out_of_sample": {key: base_mean},
        "in_sample_metric": full["metric"].get(key),
        "oos_metric": oos_mean,
        "base_oos_metric": base_mean,
        "promotable": promotable,
        "objective": objective,
        "method": "expanding",
        "n_train": n,
        "n_test": total_oos_trades,
    }
