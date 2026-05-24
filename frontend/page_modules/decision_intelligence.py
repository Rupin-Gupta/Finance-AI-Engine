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
}

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


def render():
    st.header("Decision Intelligence")
    st.caption("BUY/SELL/HOLD signal aggregating RSI, trend, momentum, volatility, sentiment & forecast.")

    symbol = st.text_input("Symbol", "AAPL", key="decision_symbol").upper().strip()
    if not st.button("Analyze"):
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

    st.divider()

    # --- Gemini explanation ---
    st.subheader("AI Analyst Explanation")
    if explanation:
        st.info(explanation)
    else:
        st.caption("No explanation available.")
