import plotly.graph_objects as go
import streamlit as st

from api_client import get

_PLOT = dict(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#ccc"))


def _pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def render():
    st.header("Confidence Calibration")
    st.caption("Are high-confidence calls actually more accurate? Which signals carry edge? "
               "What threshold would have worked best?")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        symbol = st.text_input("Symbol (blank = all)", key="cal_symbol")
    with c2:
        horizon = st.slider("Horizon (days)", 1, 60, 5, key="cal_horizon")
    with c3:
        lookback = st.slider("Lookback (days)", 30, 730, 180, step=30, key="cal_lookback")
    with c4:
        st.write("")
        st.write("")
        load = st.button("Analyze", type="primary", key="cal_load")

    if not load:
        st.info("Pick a horizon and click **Analyze** to calibrate past decisions.")
        return

    params = {"horizon_days": horizon, "lookback_days": lookback}
    if symbol.strip():
        params["symbol"] = symbol.strip().upper()

    with st.spinner("Calibrating…"):
        try:
            data = get("/v1/calibration", **params)
        except Exception as e:
            st.error(f"API error: {e}")
            return

    reliability = data.get("reliability") or {}
    if not reliability.get("count"):
        st.warning("No evaluable decisions in this window. Run the Decision job or widen the lookback.")
        return

    # ── Calibration metrics ────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Evaluated", reliability.get("count", 0))
    m2.metric("ECE (lower = better)", _pct(reliability.get("ece")))
    m3.metric("Brier Score", f"{reliability.get('brier_score', 0):.4f}")

    # ── Reliability curve ──────────────────────────────────────────────────────
    st.subheader("Reliability Curve")
    st.caption("Points on the diagonal = well calibrated. Above = under-confident, below = over-confident.")
    bins = reliability.get("bins", [])
    if bins:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[0, 1], y=[0, 1], mode="lines", name="Perfect",
            line=dict(color="#888", dash="dash"),
        ))
        fig.add_trace(go.Scatter(
            x=[b["mean_confidence"] for b in bins],
            y=[b["hit_rate"] for b in bins],
            mode="markers+lines", name="Observed",
            marker=dict(size=[8 + b["count"] for b in bins], color="#7eb8f7"),
            line=dict(color="#7eb8f7"),
            text=[f"n={b['count']}" for b in bins],
        ))
        fig.update_layout(
            height=360, margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="Predicted confidence", yaxis_title="Observed hit rate",
            xaxis=dict(range=[0, 1], tickformat=".0%"), yaxis=dict(range=[0, 1], tickformat=".0%"),
            legend=dict(orientation="h", y=1.1), **_PLOT,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Per-signal edge ────────────────────────────────────────────────────────
    signals = data.get("signals", [])
    if signals:
        st.subheader("Signal Edge")
        st.caption("Directional accuracy of each signal vs the realized move (>50% = predictive).")
        colors = ["#00c851" if s["accuracy"] >= 0.5 else "#ff4444" for s in signals]
        fig_s = go.Figure(go.Bar(
            x=[s["accuracy"] for s in signals],
            y=[s["signal"] for s in signals],
            orientation="h", marker_color=colors,
            text=[f"{s['accuracy']:.0%} (n={s['active_count']})" for s in signals],
        ))
        fig_s.add_vline(x=0.5, line_dash="dash", line_color="#888")
        fig_s.update_layout(
            height=max(200, 36 * len(signals)), margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="Directional accuracy", xaxis=dict(range=[0, 1], tickformat=".0%"),
            **_PLOT,
        )
        st.plotly_chart(fig_s, use_container_width=True)

        # Return attribution — which signals actually earned (or lost) the money
        st.caption("Return attribution: each signal's additive share of realized strategy return.")
        attr = sorted(signals, key=lambda s: s.get("attributed_return") or 0)
        a_colors = ["#00c851" if (s.get("attributed_return") or 0) >= 0 else "#ff4444" for s in attr]
        fig_a = go.Figure(go.Bar(
            x=[s.get("attributed_return") or 0 for s in attr],
            y=[s["signal"] for s in attr],
            orientation="h", marker_color=a_colors,
            text=[f"{(s.get('attributed_return') or 0):+.2%}" for s in attr],
        ))
        fig_a.add_vline(x=0, line_color="#888")
        fig_a.update_layout(
            height=max(200, 36 * len(attr)), margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="Attributed return", xaxis=dict(tickformat=".1%"), **_PLOT,
        )
        st.plotly_chart(fig_a, use_container_width=True)

    # ── Trailing 12-month rollup (R3.1) ─────────────────────────────────────────
    try:
        rollup = get("/v1/calibration/rollup", days=365).get("signals", [])
    except Exception:
        rollup = []
    rollup = [r for r in rollup if r.get("total_attributed_return") is not None
              or r.get("avg_accuracy") is not None]
    if rollup:
        st.subheader("Trailing 12-Month Rollup")
        st.caption("Per-signal mean accuracy + total return attribution across all snapshots in the window.")
        st.dataframe(
            [{
                "Signal": r["signal"],
                "Avg Accuracy": _pct(r.get("avg_accuracy")),
                "Total Attribution": f"{(r.get('total_attributed_return') or 0):+.2%}",
                "Avg Weight": f"{(r.get('avg_weight') or 0):.2f}",
                "Snapshots": r.get("snapshots", 0),
            } for r in rollup],
            use_container_width=True, hide_index=True,
        )

    # ── Signal-edge trend (history snapshots) ──────────────────────────────────
    try:
        hist = get("/v1/calibration/history", days=180).get("history", [])
    except Exception:
        hist = []
    if hist:
        by_sig: dict = {}
        for h in hist:
            if h.get("accuracy") is not None:
                by_sig.setdefault(h["signal"], []).append((h["date"], h["accuracy"]))
        if by_sig:
            st.subheader("Signal-Edge Trend")
            st.caption("Accuracy per signal over weekly snapshots — watch for decay (drift).")
            fig_h = go.Figure()
            for sig, pts in by_sig.items():
                fig_h.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                           mode="lines+markers", name=sig))
            fig_h.add_hline(y=0.5, line_dash="dash", line_color="#888")
            fig_h.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                                yaxis=dict(tickformat=".0%"), yaxis_title="Accuracy",
                                legend=dict(orientation="h", y=-0.2), **_PLOT)
            st.plotly_chart(fig_h, use_container_width=True)

    # ── Threshold tuning ───────────────────────────────────────────────────────
    tuning = data.get("threshold_tuning") or {}
    grid = tuning.get("grid", [])
    if grid:
        st.subheader("Threshold Tuning")
        current = tuning.get("current") or {}
        best = tuning.get("best") or {}
        cur_t = tuning.get("current_threshold")

        t1, t2, t3 = st.columns(3)
        t1.metric("Current threshold", f"±{cur_t}", _pct(current.get("hit_rate")) + " hit")
        if best:
            t2.metric("Best threshold", f"±{best.get('threshold')}", _pct(best.get("hit_rate")) + " hit")
            delta = None
            if best.get("hit_rate") is not None and current.get("hit_rate") is not None:
                delta = best["hit_rate"] - current["hit_rate"]
            t3.metric("Hit-rate uplift", _pct(delta) if delta is not None else "—")

        xs = [g["threshold"] for g in grid if g["hit_rate"] is not None]
        ys = [g["hit_rate"] for g in grid if g["hit_rate"] is not None]
        if xs:
            fig_t = go.Figure(go.Scatter(x=xs, y=ys, mode="markers+lines", line=dict(color="#ffa500")))
            if cur_t is not None:
                fig_t.add_vline(x=cur_t, line_dash="dash", line_color="#888", annotation_text="current")
            if best.get("threshold") is not None:
                fig_t.add_vline(x=best["threshold"], line_dash="dot", line_color="#00c851", annotation_text="best")
            fig_t.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="BUY/SELL threshold (|weighted score|)",
                yaxis_title="Hit rate", yaxis=dict(tickformat=".0%"), **_PLOT,
            )
            st.plotly_chart(fig_t, use_container_width=True)

    # ── Auto-tuned signal weights (R4) ─────────────────────────────────────────
    try:
        w = get("/v1/weights")
    except Exception:
        w = None
    if w:
        st.subheader("Signal Weights (auto-tuned)")
        using = w.get("using_tuned")
        st.caption(f"Engine is using {'**auto-tuned**' if using else 'default'} weights. "
                   "Updated weekly by walk-forward optimization (promoted only on out-of-sample improvement).")
        default_w = w.get("default_weights", {})
        active_w = w.get("active_weights", {})
        st.dataframe(
            [{"Signal": k, "Default": f"{default_w.get(k, 0):.2f}", "Active": f"{active_w.get(k, 0):.2f}"}
             for k in default_w],
            use_container_width=True, hide_index=True,
        )
        hist = w.get("history", [])
        if hist:
            latest = hist[0]
            imp = latest.get("improvement")
            st.caption(
                f"Last run: out-of-sample {(_pct(latest.get('out_of_sample_return')))} vs "
                f"base {(_pct(latest.get('base_out_of_sample_return')))} · "
                f"improvement {imp:+.2%} · {'PROMOTED' if latest.get('promoted') else 'not promoted'}"
                if imp is not None else "Last run: insufficient history."
            )

    # R7: model health (drift) panel
    _render_model_health(horizon, lookback)

    # P14: ML directional model status
    _render_ml_model()


def _render_ml_model() -> None:
    try:
        m = get("/v1/ml/model")
    except Exception:
        return
    if not m or not m.get("latest"):
        st.subheader("ML Directional Model (P14)")
        st.caption("No model trained yet — trigger `ml_train_run` once there's history.")
        return
    st.subheader("ML Directional Model (P14)")
    active, latest = m.get("active"), m.get("latest")
    if m.get("in_use") and active:
        st.success(f"🤖 Active model **{active['version']}** in use "
                   f"(weight {m['signal_weight']:.0%}) — OOS AUC {active['oos_auc']}, "
                   f"hit-rate {active['oos_hit_rate']:.0%}, Brier {active['oos_brier']}")
    else:
        st.info(f"Latest model **{latest['version']}** NOT promoted "
                f"(OOS AUC {latest['oos_auc']}, hit-rate {latest['oos_hit_rate']}). "
                f"Signal stays off until it beats the gate — by design.")
    hist = [h for h in (m.get("history") or []) if h]
    if hist:
        st.dataframe(
            [{"Version": h["version"], "Samples": h["n_samples"], "OOS AUC": h["oos_auc"],
              "Hit Rate": h["oos_hit_rate"], "Brier": h["oos_brier"],
              "Promoted": "✓" if h["promoted"] else "✗"} for h in hist],
            use_container_width=True, hide_index=True,
        )


def _render_model_health(horizon: int, lookback: int) -> None:
    """R7: model health — drift verdict, rolling accuracy, per-signal trend."""
    try:
        data = get("/v1/calibration/drift", horizon_days=horizon, lookback_days=lookback)
    except Exception:
        return
    verdict = data.get("verdict")
    if not verdict:
        return
    st.subheader("Model Health (Drift)")
    badge = {
        "healthy": ("🟢 HEALTHY", "#00c851"),
        "degrading": ("🟠 DEGRADING", "#ffa500"),
        "retraining_recommended": ("🔴 RETRAINING RECOMMENDED", "#ff4444"),
        "insufficient_data": ("⚪ INSUFFICIENT DATA", "#888888"),
    }.get(verdict, (verdict, "#888888"))
    st.markdown(
        f"<div style='background:#1a1a2e;border-left:4px solid {badge[1]};border-radius:8px;"
        f"padding:10px 14px;font-weight:700;color:{badge[1]}'>{badge[0]}</div>",
        unsafe_allow_html=True,
    )
    drift = data.get("drift") or {}
    rec, base = drift.get("recent"), drift.get("baseline")
    if rec and base:
        d1, d2, d3 = st.columns(3)
        d1.metric("Recent 30d hit rate", f"{rec['hit_rate']:.0%}", help=f"{rec['count']} calls")
        d2.metric("Baseline 90d hit rate", f"{base['hit_rate']:.0%}", help=f"{base['count']} calls")
        delta = drift.get("delta")
        d3.metric("Delta", f"{delta:+.1%}" if delta is not None else "—")

    rolling = data.get("rolling") or []
    if len(rolling) >= 2:
        fig = go.Figure(go.Scatter(
            x=[r["window_end"] for r in rolling],
            y=[r["hit_rate"] for r in rolling],
            mode="lines+markers", line=dict(color="#4da6ff"),
        ))
        fig.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="30d rolling hit rate", yaxis_tickformat=".0%",
                          plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#ccc"))
        st.plotly_chart(fig, use_container_width=True, key="drift_rolling")

    sd = data.get("signal_drift") or []
    if sd:
        st.dataframe(
            [{"Signal": s["signal"], "Snapshots": s["snapshots"],
              "First": f"{s['first_accuracy']:.0%}", "Last": f"{s['last_accuracy']:.0%}",
              "Slope": f"{s['slope']:+.3f}", "Trend": s["trend"]}
             for s in sd],
            use_container_width=True, hide_index=True,
        )
