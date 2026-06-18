import plotly.graph_objects as go
import streamlit as st

from api_client import get

_REC_COLOR = {"BUY": "#00c851", "SELL": "#ff4444", "HOLD": "#888888"}


def _pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def _ret(x) -> str:
    return "—" if x is None else f"{x:+.2%}"


def render():
    st.header("Recommendation Accuracy")
    st.caption("How past BUY/SELL/HOLD calls actually played out vs realized prices.")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        symbol = st.text_input("Symbol (blank = all)", key="perf_symbol")
    with c2:
        horizon = st.slider("Horizon (days)", 1, 60, 5, key="perf_horizon")
    with c3:
        lookback = st.slider("Lookback (days)", 30, 730, 180, step=30, key="perf_lookback")
    with c4:
        st.write("")
        st.write("")
        load = st.button("Evaluate", type="primary", key="perf_load")

    if not load:
        st.info("Pick a horizon and click **Evaluate** to score past decisions.")
        return

    params = {"horizon_days": horizon, "lookback_days": lookback}
    if symbol.strip():
        params["symbol"] = symbol.strip().upper()

    with st.spinner("Scoring past decisions…"):
        try:
            data = get("/v1/performance", **params)
        except Exception as e:
            st.error(f"API error: {e}")
            return

    overall = data.get("overall") or {}
    if not overall.get("count"):
        st.warning("No evaluable decisions in this window. Run the Decision job first, or widen the lookback.")
        st.caption(f"Pending (horizon not yet elapsed): {data.get('pending_count', 0)}")
        return

    # ── Headline metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Hit Rate", _pct(overall.get("hit_rate")))
    m2.metric("Avg Return / Call", _ret(overall.get("avg_return")))
    m3.metric("Cumulative", _ret(data.get("cumulative_return")))
    m4.metric("Evaluated", overall.get("count", 0))
    m5.metric("Pending", data.get("pending_count", 0))

    st.divider()

    # ── By recommendation ──────────────────────────────────────────────────────
    by_rec = data.get("by_recommendation", {})
    if by_rec:
        st.subheader("By Recommendation")
        cols = st.columns(len(by_rec))
        for col, (rec, stats) in zip(cols, by_rec.items()):
            color = _REC_COLOR.get(rec, "#888")
            col.markdown(
                f"<div style='border-left:4px solid {color};padding:4px 0 4px 10px'>"
                f"<b style='color:{color}'>{rec}</b><br>"
                f"Hit {_pct(stats['hit_rate'])}<br>"
                f"Ret {_ret(stats['avg_return'])}<br>"
                f"<span style='color:#888'>n = {stats['count']}</span></div>",
                unsafe_allow_html=True,
            )

    # ── By risk level ──────────────────────────────────────────────────────────
    by_risk = data.get("by_risk_level", {})
    if by_risk:
        st.subheader("By Risk Level")
        st.dataframe(
            [{"Risk": k, "Hit Rate": _pct(v["hit_rate"]),
              "Avg Return": _ret(v["avg_return"]), "Count": v["count"]}
             for k, v in by_risk.items()],
            use_container_width=True, hide_index=True,
        )

    # ── Recent scored calls ────────────────────────────────────────────────────
    recent = data.get("recent", [])
    if recent:
        st.subheader("Recent Scored Calls")
        colors = ["#00c851" if r["correct"] else "#ff4444" for r in recent]
        fig = go.Figure(go.Bar(
            x=list(range(len(recent))),
            y=[r["strategy_return"] for r in recent],
            marker_color=colors,
            hovertext=[f"{r['symbol']} {r['decision_date']} ({r['recommendation']})" for r in recent],
        ))
        fig.update_layout(
            height=240, margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="Strategy return", yaxis_tickformat=".1%",
            xaxis_showticklabels=False,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#ccc"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            [{"Symbol": r["symbol"], "Date": r["decision_date"], "Call": r["recommendation"],
              "Entry": r["entry_price"], "Exit": r["exit_price"],
              "Move": _ret(r["realized_move"]), "Return": _ret(r["strategy_return"]),
              "Hit": "✓" if r["correct"] else "✗"}
             for r in recent],
            use_container_width=True, hide_index=True,
        )

    # R9: per-call attribution
    _render_attribution(symbol.strip().upper() or None, horizon, lookback)


def _render_attribution(symbol: str | None, horizon: int, lookback: int) -> None:
    """R9: per-call return decomposition — which signals earned each call's return."""
    params = {"horizon_days": horizon, "lookback_days": lookback, "limit": 15}
    if symbol:
        params["symbol"] = symbol
    try:
        data = get("/v1/performance/attribution", **params)
    except Exception as exc:
        st.error(f"Attribution error: {exc}")
        return
    calls = data.get("calls") or []
    if not calls:
        st.caption("No closed calls to attribute yet.")
        return
    st.subheader("Per-Call Attribution")
    st.caption("Each closed call's return decomposed by signal (shares sum to the call's return).")
    for c in calls:
        ret = c.get("strategy_return")
        hit = "✓" if c.get("correct") else "✗"
        label = f"{c['symbol']} {c['decision_date']} — {c['recommendation']} → {ret:+.2%} {hit}"
        with st.expander(label):
            parts = [p for p in (c.get("breakdown") or []) if p.get("contribution")]
            if not parts:
                st.caption("HOLD / zero-conviction call — nothing to attribute.")
                continue
            st.dataframe(
                [{"Signal": p["signal"], "Score": f"{p['score']:+.1f}",
                  "Weight": f"{p['weight']:.2f}", "Share": f"{p['share']:+.0%}",
                  "Contribution": f"{p['contribution']:+.3%}"}
                 for p in parts],
                use_container_width=True, hide_index=True,
            )
