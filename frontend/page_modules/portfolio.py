import plotly.graph_objects as go
import streamlit as st

from api_client import get, post

_DEFAULT_SYMBOLS = "AAPL, MSFT, GOOGL, AMZN, NVDA"
_OBJECTIVES = {
    "Maximize Sharpe Ratio": "max_sharpe",
    "Minimize Variance": "min_variance",
    "Efficient Frontier": "efficient_frontier",
}


_RISK_COLOR = {"Low": "#00c851", "Medium": "#ffa500", "High": "#ff6b35", "Extreme": "#ff4444"}


def _render_risk(risk: dict) -> None:
    score = risk.get("risk_score") or {}
    level = score.get("level", "—")
    color = _RISK_COLOR.get(level, "#888")
    st.markdown(
        f"<div style='background:{color};border-radius:8px;padding:10px;text-align:center;"
        f"color:white;font-size:1.1rem;font-weight:700'>Portfolio Risk: {level} "
        f"({score.get('score', '—')}/100)</div>",
        unsafe_allow_html=True,
    )
    var = risk.get("var")
    corr = risk.get("correlation")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Value", f"{risk.get('total_value', 0):,.0f}")
    if var:
        m2.metric(f"1-Day VaR ({var['confidence']:.0%})", f"{var['var_pct']:.2%}",
                  delta=f"-{var['var_value']:,.0f}", delta_color="inverse")
        m3.metric("1-Day CVaR", f"{var['cvar_pct']:.2%}",
                  delta=f"-{var['cvar_value']:,.0f}", delta_color="inverse")
    if corr:
        m4.metric("Avg Pairwise Corr", f"{corr['avg_pairwise']:.2f}")

    for w in risk.get("warnings", []):
        st.warning(w)

    sector = (risk.get("sector_exposure") or {}).get("by_sector") or {}
    if sector:
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(go.Pie(labels=list(sector.keys()), values=list(sector.values()), hole=0.45))
            fig.update_layout(title="Sector Exposure", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                              font_color="#fafafa", height=320, margin=dict(t=40, b=10))
            st.plotly_chart(fig, use_container_width=True, key="risk_sector_pie")
        with c2:
            country = risk.get("country_exposure") or {}
            caps = risk.get("market_cap_exposure") or {}
            st.markdown("**Country exposure**")
            st.write({k: f"{v:.0%}" for k, v in country.items()})
            st.markdown("**Market-cap exposure**")
            st.write({k: f"{v:.0%}" for k, v in caps.items()})


def render():
    st.header("Portfolio Optimization")
    st.caption("Mean-variance optimization via scipy. Weights, metrics, and efficient frontier.")

    # --- Portfolio Risk (R6) ---
    st.subheader("Portfolio Risk")
    rc1, rc2, rc3 = st.columns([1, 2, 1])
    with rc1:
        risk_source = st.radio("Holdings", ["watchlist", "paper"], horizontal=True, key="risk_source")
    with rc2:
        risk_lookback = st.slider("Risk lookback (days)", 60, 730, 365, step=30, key="risk_lookback")
    with rc3:
        run_risk = st.button("Analyze Risk", type="primary", key="risk_run")
    if run_risk:
        try:
            with st.spinner("Assessing portfolio risk…"):
                risk = get("/v1/portfolio/risk", source=risk_source, lookback_days=risk_lookback)
            _render_risk(risk)
        except Exception as e:
            st.error(str(e))

    st.divider()

    # --- Stop-Loss Monitor (P3) ---
    st.subheader("Stop-Loss Monitor")
    sc1, sc2 = st.columns([1, 3])
    with sc1:
        stop_source = st.radio("Holdings ", ["watchlist", "paper"], horizontal=True, key="stop_source")
    with sc2:
        run_stops = st.button("Check Stops", type="primary", key="stops_run_btn")
    if run_stops:
        try:
            with st.spinner("Evaluating stops…"):
                data = get("/v1/portfolio/stops", source=stop_source)
            _render_stops(data)
        except Exception as e:
            st.error(str(e))

    st.divider()

    col1, col2 = st.columns([3, 1])
    with col1:
        symbols_input = st.text_input(
            "Symbols (comma-separated, min 2)",
            _DEFAULT_SYMBOLS,
            key="portfolio_symbols",
        )
    with col2:
        objective_label = st.selectbox("Objective", list(_OBJECTIVES.keys()), key="portfolio_obj")

    col3, col4 = st.columns(2)
    with col3:
        lookback = st.slider("Lookback (days)", 60, 730, 365, step=30, key="portfolio_lookback")
    with col4:
        rfr = st.number_input(
            "Risk-free rate", min_value=0.0, max_value=0.20, value=0.05,
            step=0.005, format="%.3f", key="portfolio_rfr",
        )

    if not st.button("Optimize", key="portfolio_run"):
        return

    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
    if len(symbols) < 2:
        st.error("Need at least 2 symbols.")
        return

    objective = _OBJECTIVES[objective_label]

    with st.spinner("Running optimization..."):
        try:
            data = post("/v1/portfolio/optimize", {
                "symbols": symbols,
                "objective": objective,
                "risk_free_rate": rfr,
                "lookback_days": lookback,
            })
        except Exception as exc:
            st.error(f"API error: {exc}")
            return

    if data.get("missing_symbols"):
        st.warning(f"No data for: {', '.join(data['missing_symbols'])} — excluded from optimization.")

    weights = data.get("weights", {})
    metrics = data.get("metrics", {})
    ef = data.get("efficient_frontier", [])
    used_symbols = data.get("symbols", [])

    if not weights:
        st.warning("No result returned.")
        return

    # --- Metrics ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Expected Return (ann.)", f"{metrics.get('expected_annual_return', 0):.1%}")
    m2.metric("Volatility (ann.)", f"{metrics.get('annual_volatility', 0):.1%}")
    m3.metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.3f}")
    m4.metric("Data Points", data.get("data_points", "—"))

    # --- Weights ---
    st.subheader("Optimal Weights")
    chart_col, table_col = st.columns([3, 2])

    with chart_col:
        sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        labels = [s for s, _ in sorted_w]
        values = [w for _, w in sorted_w]

        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values,
            textinfo="label+percent",
            hole=0.35,
        ))
        fig_pie.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            showlegend=False,
            height=320,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with table_col:
        weight_rows = [
            {"Symbol": s, "Weight": f"{w:.2%}", "Weight (raw)": round(w, 4)}
            for s, w in sorted_w
        ]
        st.dataframe(
            [{"Symbol": r["Symbol"], "Weight": r["Weight"]} for r in weight_rows],
            use_container_width=True,
            hide_index=True,
        )

    # --- Efficient Frontier ---
    if ef and len(ef) >= 3:
        st.subheader("Efficient Frontier")

        ef_vols = [p["volatility"] for p in ef]
        ef_rets = [p["return"] for p in ef]
        opt_vol = metrics.get("annual_volatility", 0)
        opt_ret = metrics.get("expected_annual_return", 0)

        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(
            x=ef_vols, y=ef_rets,
            mode="lines",
            name="Efficient Frontier",
            line=dict(color="#1f77b4", width=2),
        ))
        fig_ef.add_trace(go.Scatter(
            x=[opt_vol], y=[opt_ret],
            mode="markers",
            name="Optimal Portfolio",
            marker=dict(color="#ff7f0e", size=12, symbol="star"),
        ))
        fig_ef.update_layout(
            xaxis_title="Annual Volatility",
            yaxis_title="Expected Annual Return",
            xaxis_tickformat=".1%",
            yaxis_tickformat=".1%",
            height=380,
            margin=dict(t=30, b=40, l=60, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_ef, use_container_width=True)

    # --- Per-symbol breakdown ---
    with st.expander("Symbol breakdown"):
        st.caption(f"Symbols used: {', '.join(used_symbols)} · Lookback: {data.get('lookback_days')}d · RF rate: {data.get('risk_free_rate'):.1%}")


def _render_stops(data: dict) -> None:
    positions = data.get("positions") or []
    if not positions:
        for w in data.get("warnings", []):
            st.info(w)
        if not data.get("warnings"):
            st.caption("No positions with an entry price to monitor.")
        return
    breached = data.get("breached_count", 0)
    if breached:
        st.error(f"🛑 {breached} position(s) breached their stop: {', '.join(data.get('breached', []))}")
    else:
        st.success("✅ No stops breached.")
    st.dataframe(
        [{"Symbol": p["symbol"], "Entry": p["entry"], "Current": p["current"],
          "Stop": p["stop_level"], "Stop %": f"{p['stop_pct']:.1%}",
          "Type": "trailing" if p["trailing"] else "fixed",
          "Dist to stop": f"{p['distance_pct']:+.1%}" if p["distance_pct"] is not None else "—",
          "Locked P/L": f"{p['stop_pl_pct']:+.1%}",
          "Src": "auto" if p.get("recommended") else "set",
          "Breached": "🛑" if p["breached"] else "✓"}
         for p in positions],
        use_container_width=True, hide_index=True,
    )
