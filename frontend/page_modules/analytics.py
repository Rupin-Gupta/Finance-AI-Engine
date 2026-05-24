import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import get


def render():
    st.header("Analytics Dashboard")
    symbol = st.text_input("Symbol", "AAPL", key="analytics_symbol").upper().strip()
    days = st.slider("Days", 30, 365, 60)

    if st.button("Load"):
        data = get(f"/v1/analytics/{symbol}", days=days)
        rows = data.get("data", [])
        if not rows:
            st.warning("No data found. Try triggering an ingest first.")
            return

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Moving averages chart
        fig = go.Figure()
        if "sma_20" in df.columns and df["sma_20"].notna().any():
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df["sma_20"], name="SMA 20", line=dict(dash="dash")))
        if "ema_20" in df.columns and df["ema_20"].notna().any():
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df["ema_20"], name="EMA 20", line=dict(dash="dot")))
        if fig.data:
            fig.update_layout(title=f"{symbol} Moving Averages", xaxis_title="Date", yaxis_title="Price")
            st.plotly_chart(fig, use_container_width=True)

        # RSI chart
        if "rsi_14" in df.columns and df["rsi_14"].notna().any():
            fig2 = go.Figure(go.Scatter(x=df["timestamp"], y=df["rsi_14"], name="RSI 14"))
            fig2.add_hline(y=70, line_color="red", line_dash="dash")
            fig2.add_hline(y=30, line_color="green", line_dash="dash")
            fig2.update_layout(title="RSI (14)", yaxis_range=[0, 100])
            st.plotly_chart(fig2, use_container_width=True)

        # Volatility chart
        if "volatility_20" in df.columns and df["volatility_20"].notna().any():
            fig3 = go.Figure(go.Scatter(x=df["timestamp"], y=df["volatility_20"], name="Volatility 20", fill="tozeroy"))
            fig3.update_layout(title="Volatility (20-day annualized)")
            st.plotly_chart(fig3, use_container_width=True)

        # Momentum chart
        if "momentum_10" in df.columns and df["momentum_10"].notna().any():
            fig4 = go.Figure(go.Bar(x=df["timestamp"], y=df["momentum_10"], name="Momentum 10"))
            fig4.update_layout(title="Momentum (10-day)")
            st.plotly_chart(fig4, use_container_width=True)

        st.dataframe(df.set_index("timestamp").dropna(how="all", axis=1), use_container_width=True)
