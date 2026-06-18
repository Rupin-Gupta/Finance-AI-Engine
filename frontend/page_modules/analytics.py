import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import get

_UP = "#00c851"
_DOWN = "#ff4444"
_NEUTRAL = "#ffa500"


def render():
    st.header("Analytics Dashboard")

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        symbol = st.text_input("Symbol", "AAPL", key="analytics_symbol").upper().strip()
    with c2:
        days = st.slider("Days", 30, 365, 90, key="analytics_days")
    with c3:
        st.write("")
        st.write("")
        load = st.button("Load", type="primary", key="analytics_load")

    if not load:
        st.info("Enter a symbol and click **Load**.")
        return

    with st.spinner(f"Loading analytics + OHLCV for {symbol}…"):
        try:
            analytics_data = get(f"/v1/analytics/{symbol}", days=days)
            ohlcv_rows = get(f"/v1/stocks/{symbol}/ohlcv", days=days)
        except Exception as e:
            st.error(f"API error: {e}")
            return

    rows = analytics_data.get("data", [])
    if not rows:
        st.warning("No analytics data. Trigger **Analytics Run** job first.")
        return

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df_ohlcv = pd.DataFrame(ohlcv_rows) if ohlcv_rows else pd.DataFrame()
    if not df_ohlcv.empty:
        df_ohlcv["timestamp"] = pd.to_datetime(df_ohlcv["timestamp"])
        for col in ("open", "high", "low", "close", "volume"):
            if col in df_ohlcv.columns:
                df_ohlcv[col] = df_ohlcv[col].astype(float)

    _PLOT = dict(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#ccc"))

    # ── Chart 1: Price + Moving Averages ──────────────────────────────────────
    st.subheader("Price & Moving Averages")
    fig1 = go.Figure()
    if not df_ohlcv.empty:
        fig1.add_trace(go.Scatter(
            x=df_ohlcv["timestamp"], y=df_ohlcv["close"],
            name="Close", line=dict(color="#8888ff", width=1.5),
        ))
    if "sma_20" in df.columns and df["sma_20"].notna().any():
        fig1.add_trace(go.Scatter(
            x=df["timestamp"], y=df["sma_20"],
            name="SMA 20", line=dict(color="#ffa500", dash="dash", width=1.8),
        ))
    if "ema_20" in df.columns and df["ema_20"].notna().any():
        fig1.add_trace(go.Scatter(
            x=df["timestamp"], y=df["ema_20"],
            name="EMA 20", line=dict(color="#00c851", dash="dot", width=1.8),
        ))
    fig1.update_layout(
        height=360, margin=dict(l=0, r=0, t=20, b=0),
        xaxis_title="Date", yaxis_title="Price ($)",
        legend=dict(orientation="h", y=1.08),
        **_PLOT,
    )
    st.plotly_chart(fig1, use_container_width=True)

    # Volume bars
    if not df_ohlcv.empty and "volume" in df_ohlcv.columns:
        closes = df_ohlcv["close"].tolist()
        opens = df_ohlcv["open"].tolist() if "open" in df_ohlcv.columns else closes
        vol_colors = [_UP if c >= o else _DOWN for c, o in zip(closes, opens)]
        fig_vol = go.Figure(go.Bar(
            x=df_ohlcv["timestamp"], y=df_ohlcv["volume"],
            marker_color=vol_colors, name="Volume",
        ))
        fig_vol.update_layout(
            height=130, margin=dict(l=0, r=0, t=4, b=0),
            yaxis_title="Volume", **_PLOT,
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    left, right = st.columns(2)

    # ── Chart 2: RSI with colored zones ──────────────────────────────────────
    with left:
        st.subheader("RSI (14)")
        if "rsi_14" in df.columns and df["rsi_14"].notna().any():
            fig2 = go.Figure()
            fig2.add_hrect(y0=70, y1=100, fillcolor="rgba(255,68,68,0.12)", line_width=0)
            fig2.add_hrect(y0=0,  y1=30,  fillcolor="rgba(0,200,81,0.12)",  line_width=0)
            fig2.add_hline(y=70, line_color="#ff4444", line_dash="dash", line_width=1,
                           annotation_text="Overbought", annotation_position="top left")
            fig2.add_hline(y=30, line_color="#00c851", line_dash="dash", line_width=1,
                           annotation_text="Oversold", annotation_position="bottom left")
            rsi_vals = df["rsi_14"].astype(float)
            rsi_colors = [
                "#00c851" if v < 30 else "#ff4444" if v > 70 else "#7eb8f7"
                for v in rsi_vals
            ]
            fig2.add_trace(go.Scatter(
                x=df["timestamp"], y=rsi_vals,
                name="RSI 14",
                line=dict(color="#7eb8f7", width=2),
                fill="tozeroy", fillcolor="rgba(126,184,247,0.06)",
            ))
            fig2.update_layout(
                height=280, margin=dict(l=0, r=0, t=20, b=0),
                yaxis=dict(range=[0, 100]), **_PLOT,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No RSI data.")

    # ── Chart 3: Volatility with color bands ─────────────────────────────────
    with right:
        st.subheader("Volatility (20-day ann.)")
        if "volatility_20" in df.columns and df["volatility_20"].notna().any():
            vol_vals = df["volatility_20"].astype(float)
            vol_colors = [
                _UP if v < 0.25 else _NEUTRAL if v < 0.45 else _DOWN
                for v in vol_vals
            ]
            fig3 = go.Figure(go.Bar(
                x=df["timestamp"], y=vol_vals,
                marker_color=vol_colors, name="Volatility",
            ))
            fig3.add_hline(y=0.25, line_dash="dash", line_color=_UP,     line_width=1,
                           annotation_text="Low", annotation_position="top right")
            fig3.add_hline(y=0.45, line_dash="dash", line_color=_DOWN,   line_width=1,
                           annotation_text="Extreme", annotation_position="top right")
            fig3.update_layout(
                height=280, margin=dict(l=0, r=0, t=20, b=0), **_PLOT,
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No volatility data.")

    # ── Chart 4: Momentum ─────────────────────────────────────────────────────
    st.subheader("Momentum (10-day)")
    if "momentum_10" in df.columns and df["momentum_10"].notna().any():
        mom_vals = df["momentum_10"].astype(float)
        mom_colors = [_UP if v >= 0 else _DOWN for v in mom_vals]
        fig4 = go.Figure(go.Bar(
            x=df["timestamp"], y=mom_vals,
            marker_color=mom_colors, name="Momentum",
        ))
        fig4.add_hline(y=0, line_color="gray", line_dash="dash", line_width=1)
        fig4.update_layout(
            height=240, margin=dict(l=0, r=0, t=20, b=0), **_PLOT,
        )
        st.plotly_chart(fig4, use_container_width=True)

    with st.expander("Raw data"):
        st.dataframe(df.set_index("timestamp").dropna(how="all", axis=1), use_container_width=True)
