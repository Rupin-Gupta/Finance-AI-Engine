import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import get

_SIGNAL_LABELS = {
    "rsi": "RSI",
    "trend": "Price vs SMA",
    "momentum": "Momentum",
    "volatility": "Volatility",
    "sentiment": "Sentiment",
    "forecast": "Forecast",
    "ema_crossover": "EMA Cross",
    "volume": "Volume",
    "india_flow": "India Flow",
}


def _na(v) -> str:
    return "—" if v is None else f"{v:,.0f}"

_RISK_COLOR = {
    "Low": "#28a745",
    "Medium": "#fd7e14",
    "High": "#dc3545",
    "Extreme": "#6f0000",
}

_REC_COLOR = {
    "BUY": "#28a745",
    "SELL": "#dc3545",
    "HOLD": "#fd7e14",
}


def _signal_badge(score: float) -> str:
    if score > 0:
        return "🟢 Bullish"
    if score < 0:
        return "🔴 Bearish"
    return "🟡 Neutral"


def _render_comparison(symbols: list[str]) -> None:
    rows = []
    progress = st.progress(0)
    for i, sym in enumerate(symbols):
        try:
            d = get(f"/v1/decision/{sym}")
            signals = d.get("signals", {})
            forecast = d.get("forecast", [])
            rows.append({
                "Symbol": sym,
                "Rec": d.get("recommendation", "—"),
                "Conf": d.get("confidence"),
                "Risk": d.get("risk_level", "—"),
                "RSI": signals.get("rsi", {}).get("value"),
                "Sentiment": d.get("sentiment_score"),
                "7d Forecast": forecast[-1].get("predicted_close") if forecast else None,
                "Price": d.get("current_close"),
            })
        except Exception:
            rows.append({"Symbol": sym, "Rec": "ERROR", "Conf": None, "Risk": "—",
                         "RSI": None, "Sentiment": None, "7d Forecast": None, "Price": None})
        progress.progress((i + 1) / len(symbols))
    progress.empty()

    if not rows:
        return

    df = pd.DataFrame(rows)

    def _style_rec(val):
        m = {
            "BUY":   "background-color:#1a4a1a;color:#28a745",
            "SELL":  "background-color:#4a1a1a;color:#dc3545",
            "HOLD":  "background-color:#4a3000;color:#fd7e14",
            "ERROR": "color:#888",
        }
        return m.get(val, "")

    fmt = df.copy()
    fmt["Conf"] = fmt["Conf"].apply(lambda x: f"{x:.0%}" if x is not None else "—")
    fmt["RSI"] = fmt["RSI"].apply(lambda x: f"{x:.1f}" if x is not None else "—")
    fmt["Sentiment"] = fmt["Sentiment"].apply(lambda x: f"{x:+.3f}" if x is not None else "—")
    fmt["7d Forecast"] = fmt["7d Forecast"].apply(lambda x: f"${x:.2f}" if x is not None else "—")
    fmt["Price"] = fmt["Price"].apply(lambda x: f"${x:.2f}" if x is not None else "—")

    st.dataframe(fmt.style.map(_style_rec, subset=["Rec"]), use_container_width=True, hide_index=True)


def render():
    st.header("Decision Intelligence")
    st.caption("BUY/SELL/HOLD signal aggregating RSI, trend, momentum, volatility, sentiment & forecast.")

    # --- Multi-symbol comparison ---
    st.subheader("Multi-Symbol Comparison")
    compare_input = st.text_input(
        "Symbols (comma-separated)", "AAPL,MSFT,GOOGL,TSLA",
        key="compare_symbols",
    )
    if st.button("Compare", key="compare_btn"):
        syms = [s.strip().upper() for s in compare_input.split(",") if s.strip()]
        if syms:
            with st.spinner(f"Fetching decisions for {len(syms)} symbols..."):
                _render_comparison(syms)

    st.divider()

    # --- Single-symbol analysis ---
    st.subheader("Single Symbol Analysis")
    symbol = st.text_input("Symbol", "AAPL", key="decision_symbol").upper().strip()
    if not st.button("Analyze", key="decision_analyze"):
        return

    with st.spinner(f"Running decision engine for {symbol}..."):
        try:
            data = get(f"/v1/decision/{symbol}")
        except Exception as exc:
            st.error(f"API error: {exc}")
            return

    if not data:
        st.warning("No data returned.")
        return

    rec = data.get("recommendation", "HOLD")
    confidence = data.get("confidence", 0.0)
    risk = data.get("risk_level", "Medium")
    explanation = data.get("explanation", "")
    signals = data.get("signals", {})
    forecast = data.get("forecast", [])
    sentiment_history = data.get("sentiment_history", [])
    current_close = data.get("current_close")
    sentiment_score = data.get("sentiment_score")
    sentiment_sources = data.get("sentiment_sources", [])

    # --- India market overlay (P5): shown for Indian symbols ---
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        try:
            ind = get("/v1/india/signals")
        except Exception:
            ind = None
        if ind:
            flow = ind.get("india_flow", {}) or {}
            with st.expander("🇮🇳 India market context (FII/DII · NIFTY PCR · Gift Nifty)", expanded=False):
                ic = st.columns(4)
                ic[0].metric("FII net (₹cr)", _na(ind.get("fii_net_cr")))
                ic[1].metric("DII net (₹cr)", _na(ind.get("dii_net_cr")))
                pcr = ind.get("pcr")
                ic[2].metric("NIFTY PCR", "—" if pcr is None else f"{pcr:.2f}")
                gp = ind.get("gift_nifty_pct")
                ic[3].metric("Gift Nifty", f"{gp:+.2%}" if gp is not None else "—")
                st.caption(
                    f"Overlay signal: {_signal_badge(flow.get('score') or 0)} "
                    f"(score {flow.get('score')}, weight {flow.get('weight')}) · "
                    f"source {ind.get('source') or '—'} · {ind.get('date') or 'no data'}")

    # --- Top row: recommendation badge + confidence + risk ---
    col1, col2, col3 = st.columns(3)
    rec_color = _REC_COLOR.get(rec, "#888")
    risk_color = _RISK_COLOR.get(risk, "#888")

    with col1:
        st.markdown(
            f"<div style='background:{rec_color};border-radius:10px;padding:18px;text-align:center;"
            f"color:white;font-size:2rem;font-weight:bold'>{rec}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.metric("Confidence", f"{confidence:.0%}")
        st.progress(float(confidence))
    with col3:
        st.markdown(
            f"<div style='background:{risk_color};border-radius:8px;padding:12px;text-align:center;"
            f"color:white;font-size:1.2rem'>Risk: {risk}</div>",
            unsafe_allow_html=True,
        )
        regime = data.get("market_regime")
        if regime:
            st.caption(f"Market regime: **{regime.replace('_', ' ').upper()}** (weights tilted)")
        ev = data.get("upcoming_event")
        if ev:
            st.warning(
                f"⚠️ {ev['title']} in {ev['days_to_event']}d "
                f"({ev['impact']} impact) — confidence gated",
                icon="📅",
            )

    # --- Position sizing (how much) ---
    sizing = data.get("position_sizing")
    if sizing:
        rec_pct = sizing.get("recommended_pct", 0)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Suggested Size", f"{rec_pct:.1%}", help="% of portfolio — most conservative of the models below")
        s2.metric("Kelly (½)", f"{sizing.get('kelly_pct', 0):.1%}")
        s3.metric("Vol-target", f"{sizing.get('vol_target_pct', 0):.1%}")
        s4.metric("Risk-budget", f"{sizing.get('risk_budget_pct', 0):.1%}")
        st.caption(sizing.get("reason", ""))

    # --- Data reliability (P9): warn only when there's a problem ---
    try:
        dq = get(f"/v1/data-quality/{symbol}", reconcile="false")
    except Exception:
        dq = None
    if dq and not dq.get("ok") and dq.get("issues"):
        st.warning("⚠️ Data quality: " + "; ".join(dq["issues"]) +
                   " — this decision may rest on unreliable data.")

    st.divider()

    # --- Signal scorecard ---
    st.subheader("Signal Scorecard")
    sig_cols = st.columns(len(signals) or 1)
    for idx, (name, sig) in enumerate(signals.items()):
        with sig_cols[idx % len(sig_cols)]:
            label = _SIGNAL_LABELS.get(name, name.title())
            badge = _signal_badge(sig.get("score", 0))
            val = sig.get("value")
            val_str = f"{val:.4f}" if val is not None else "N/A"
            st.metric(label=label, value=badge, delta=val_str)

    st.divider()

    # --- Two-column layout: forecast + sentiment ---
    left, right = st.columns(2)

    with left:
        st.subheader("7-Day Price Forecast")
        if forecast:
            dates = [r["date"] for r in forecast]
            pred = [r["predicted_close"] for r in forecast]
            lower = [r["lower"] for r in forecast]
            upper = [r["upper"] for r in forecast]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates + dates[::-1],
                y=upper + lower[::-1],
                fill="toself",
                fillcolor="rgba(0,100,255,0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                name="80% CI",
                hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=dates, y=pred,
                mode="lines+markers",
                name="Predicted Close",
                line=dict(color="#0064ff", width=2),
            ))
            if current_close is not None:
                fig.add_hline(
                    y=current_close,
                    line_dash="dash",
                    line_color="gray",
                    annotation_text="Current",
                )
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=20, b=0),
                legend=dict(orientation="h"),
                xaxis_title="Date", yaxis_title="Price ($)",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No forecast data. Run ingest to populate OHLCV history.")

    with right:
        st.subheader("Sentiment Timeline")
        if sentiment_history:
            dates_s = [r["date"] for r in reversed(sentiment_history)]
            scores_s = [r["score"] for r in reversed(sentiment_history)]
            colors = ["#28a745" if s > 0 else "#dc3545" if s < 0 else "#888" for s in scores_s]

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=dates_s, y=scores_s,
                marker_color=colors,
                name="Daily Sentiment",
            ))
            fig2.add_hline(y=0, line_color="gray", line_dash="dash")
            fig2.update_layout(
                height=300, margin=dict(l=0, r=0, t=20, b=0),
                yaxis=dict(range=[-1, 1]),
                xaxis_title="Date", yaxis_title="Score",
            )
            st.plotly_chart(fig2, use_container_width=True)
        elif sentiment_score is not None:
            st.metric("Latest Sentiment Score", f"{sentiment_score:.3f}")
            st.info("Run the sentiment job to populate history.")
        else:
            st.info("No sentiment data. Sentiment job has not run yet.")

        if sentiment_sources:
            st.caption("Today's sentiment by source")
            _SOURCE_LABELS = {
                "yahoo_finance": "Yahoo Finance",
                "reddit": "Reddit (WSB/stocks)",
                "stocktwits": "StockTwits",
                "google_news": "Google News",
                "global_news": "Global News (Reuters/CNBC)",
                "india_news": "India News (ET/LiveMint)",
            }
            src_names = [_SOURCE_LABELS.get(r["source"], r["source"]) for r in sentiment_sources]
            src_scores = [r["score"] for r in sentiment_sources]
            src_counts = [r["headline_count"] for r in sentiment_sources]
            src_colors = ["#28a745" if s > 0 else "#dc3545" if s < 0 else "#888" for s in src_scores]

            fig3 = go.Figure(go.Bar(
                x=src_names,
                y=src_scores,
                marker_color=src_colors,
                text=[f"{s:+.3f}<br>({c} posts)" for s, c in zip(src_scores, src_counts)],
                textposition="outside",
            ))
            fig3.add_hline(y=0, line_color="gray", line_dash="dash")
            fig3.update_layout(
                height=220, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(range=[-1.3, 1.3]),
            )
            st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # --- Gemini explanation ---
    st.subheader("AI Analyst Explanation")
    if explanation:
        st.info(explanation)
    else:
        st.caption("No explanation available.")

    st.divider()

    # --- Multi-Timeframe Confluence (P8) ---
    st.subheader("Multi-Timeframe Confluence")
    st.caption("Same engine across daily / weekly / monthly (resampled) — agreement across "
               "horizons = higher conviction.")
    mt1, mt2 = st.columns([1, 3])
    with mt1:
        want_intraday = st.checkbox("Include 1h intraday", key="tf_intraday")
    with mt2:
        run_tf = st.button("Analyze Timeframes", key="tf_run")
    if run_tf:
        with st.spinner("Computing per-timeframe signals…"):
            try:
                tf = get(f"/v1/decision/{symbol}/timeframes", intraday=str(want_intraday).lower())
            except Exception as exc:
                st.error(f"Timeframes error: {exc}")
                tf = None
        if tf:
            _render_timeframes(tf)

    st.divider()

    # --- Investment Committee (R10) ---
    st.subheader("Investment Committee")
    st.caption("4 specialist agents (Technical / Fundamental / Macro / Sentiment) + a Risk Officer "
               "with deterministic veto authority. Verdict is stored with the decision.")
    if st.button("Convene Committee", key="committee_run"):
        with st.spinner("Committee deliberating (5 agents)…"):
            try:
                com = get(f"/v1/decision/{symbol}/committee")
            except Exception as exc:
                st.error(f"Committee error: {exc}")
                com = None
        if com:
            _render_committee(com)

    st.divider()

    # --- Backtesting ---
    st.subheader("Backtesting")
    st.caption("Replay historical signals day-by-day. BUY/SELL → next-day return; HOLD → no trade. Forecast signal excluded (no historical Prophet data stored).")

    bt_days = st.slider("Look-back window (days)", min_value=30, max_value=730, value=365, step=30, key="bt_days")
    if st.button("Run Backtest", key="bt_run"):
        with st.spinner(f"Backtesting {symbol} over {bt_days} days..."):
            try:
                bt = get(f"/v1/decision/backtest/{symbol}?days={bt_days}")
            except Exception as exc:
                st.error(f"Backtest error: {exc}")
                bt = None

        if bt:
            _render_backtest(bt)


def _render_backtest(bt: dict) -> None:
    total_ret = bt.get("total_return", 0)          # net of costs
    gross_ret = bt.get("gross_return")
    cost_drag = bt.get("cost_drag")
    win_rate = bt.get("win_rate")
    sharpe = bt.get("sharpe_ratio")
    drawdown = bt.get("max_drawdown", 0)
    trades = bt.get("trades", 0)
    days_analyzed = bt.get("days_analyzed", 0)

    st.caption("Net of transaction costs (slippage + brokerage/STT/exchange). Next-bar-open fills, no lookahead.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Net Return", f"{total_ret:+.2%}",
        f"cost drag {cost_drag:+.2%}" if cost_drag is not None else None,
        delta_color="inverse",
    )
    c2.metric("Win Rate (net)", f"{win_rate:.1%}" if win_rate is not None else "N/A")
    c3.metric("Sharpe (net)", f"{sharpe:.2f}" if sharpe is not None else "N/A")
    c4.metric("Max Drawdown", f"{drawdown:.2%}")
    c5.metric("Trades / Days", f"{trades} / {days_analyzed}")

    if gross_ret is not None:
        cm = bt.get("cost_model", {})
        st.caption(
            f"Gross (ideal fills): **{gross_ret:+.2%}** → Net: **{total_ret:+.2%}**  ·  "
            f"slippage {cm.get('slippage_bps', '—')}bps/side, "
            f"round-trip fees {cm.get('round_trip_fee_pct', 0) * 100:.2f}%"
        )

    equity = bt.get("equity_curve", [])
    if equity:
        dates_e = [r["date"] for r in equity]
        vals_e = [r["cumulative"] for r in equity]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates_e, y=vals_e,
            mode="lines",
            name="Equity",
            line=dict(color="#0064ff", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,100,255,0.08)",
        ))
        fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="Flat")
        fig.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=20, b=0),
            yaxis_title="Cumulative Return (×1)",
            xaxis_title="Date",
        )
        st.plotly_chart(fig, use_container_width=True)

    daily = bt.get("daily", [])
    if daily:
        with st.expander("Daily signal log"):
            import pandas as pd
            df = pd.DataFrame(daily)
            for col in ("gross_return", "daily_return"):
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: f"{x:+.2%}" if x is not None else "—")
            df = df.rename(columns={"gross_return": "gross", "daily_return": "net"})
            st.dataframe(df, use_container_width=True)

    assumptions = bt.get("assumptions", [])
    if assumptions:
        with st.expander("⚠ Backtest assumptions & limitations"):
            for a in assumptions:
                st.markdown(f"- {a}")


def _render_committee(com: dict) -> None:
    vetoed = com.get("vetoed")
    final = com.get("final_recommendation", "—")
    engine = com.get("engine_recommendation", "—")
    if vetoed:
        st.error(f"🛑 RISK OFFICER VETO — engine said {engine}, committee verdict: **{final}**")
        for r in com.get("veto_reasons", []):
            st.caption(f"• {r}")
    else:
        st.success(f"✅ Committee endorses: **{final}**")

    votes = com.get("votes") or {}
    vote_cols = st.columns(len(votes) or 1)
    vote_icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", None: "⚪"}
    for col, (role, vote) in zip(vote_cols, votes.items()):
        col.metric(role.title(), f"{vote_icon.get(vote, '⚪')} {vote or '—'}")

    for role, text in (com.get("views") or {}).items():
        if text:
            with st.expander(f"{role.title()} Analyst"):
                st.write(text)
    if com.get("risk_officer"):
        with st.expander("Risk Officer", expanded=True):
            st.write(com["risk_officer"])


def _render_timeframes(tf: dict) -> None:
    conf = tf.get("confluence") or {}
    verdict = conf.get("verdict", "—")
    vcolor = {"STRONG_BUY": "#00c851", "LEANS_BUY": "#5fb85f", "HOLD": "#ffa500",
              "LEANS_SELL": "#e06666", "STRONG_SELL": "#ff4444", "MIXED": "#888",
              "INSUFFICIENT": "#888"}.get(verdict, "#888")
    st.markdown(
        f"<div style='background:{vcolor};border-radius:8px;padding:10px;text-align:center;"
        f"color:white;font-weight:800'>Confluence: {verdict.replace('_', ' ')} "
        f"({conf.get('agreement', 0):.0%} agree)</div>",
        unsafe_allow_html=True,
    )
    rows = tf.get("timeframes") or []
    if not rows:
        st.caption("Not enough history for any timeframe.")
        return
    cols = st.columns(len(rows))
    for col, s in zip(cols, rows):
        rc = _REC_COLOR.get(s["recommendation"], "#888")
        with col:
            st.markdown(
                f"<div style='text-align:center'><div style='color:#aaa;font-size:.8rem'>"
                f"{s['timeframe'].upper()}</div>"
                f"<div style='color:{rc};font-size:1.3rem;font-weight:800'>{s['recommendation']}</div>"
                f"<div style='color:#ccc;font-size:.8rem'>conf {s['confidence']:.0%} · {s['bars']} bars</div></div>",
                unsafe_allow_html=True,
            )
