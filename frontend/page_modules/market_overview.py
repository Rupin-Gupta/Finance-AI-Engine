import plotly.graph_objects as go
import streamlit as st

from api_client import get, post

_UP = "#00c851"
_DOWN = "#ff4444"
_NEUTRAL = "#888888"
_DEFAULT_SYMBOLS = "AAPL,MSFT,GOOGL,TSLA,AMZN"


def _card(sym: str, price, change_pct: float | None) -> str:
    if price is None:
        color, price_str, delta_str = _NEUTRAL, "N/A", "—"
    else:
        price = float(price)
        if change_pct is None:
            color, price_str, delta_str = _NEUTRAL, f"${price:.2f}", "—"
        else:
            change_pct = float(change_pct)
            color = _UP if change_pct >= 0 else _DOWN
            arrow = "▲" if change_pct >= 0 else "▼"
            price_str = f"${price:.2f}"
            delta_str = f"{arrow} {abs(change_pct):.2f}%"

    return (
        f"<div style='background:#1a1a2e;border-radius:12px;padding:16px 20px;"
        f"border-left:4px solid {color};margin-bottom:6px'>"
        f"<div style='font-size:.8rem;color:#aaa;letter-spacing:1px;font-weight:700'>{sym}</div>"
        f"<div style='font-size:1.6rem;font-weight:800;color:#fff;margin:4px 0'>{price_str}</div>"
        f"<div style='font-size:.95rem;color:{color};font-weight:600'>{delta_str}</div>"
        f"</div>"
    )


_REGIME_STYLE = {
    "bull": (_UP, "🐂 BULL"),
    "bear": (_DOWN, "🐻 BEAR"),
    "high_vol": ("#ffa500", "⚡ HIGH VOL"),
    "sideways": (_NEUTRAL, "↔ SIDEWAYS"),
}


def _regime_badge(market_label: str, regime: str, reason: str | None) -> str:
    color, text = _REGIME_STYLE.get(regime, (_NEUTRAL, regime.upper()))
    reason_html = f"<span style='color:#aaa;font-size:.8rem;margin-left:8px'>{reason}</span>" if reason else ""
    return (
        f"<div style='background:#1a1a2e;border-radius:10px;padding:8px 14px;margin-bottom:8px;"
        f"border-left:4px solid {color}'>"
        f"<span style='color:#aaa;font-size:.8rem;letter-spacing:1px'>{market_label} REGIME</span> "
        f"<span style='color:{color};font-weight:800;margin-left:8px'>{text}</span>{reason_html}"
        f"</div>"
    )


def render():
    st.header("Market Overview")

    raw = st.text_input("Symbols (comma-separated)", _DEFAULT_SYMBOLS, key="mkt_syms")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        refresh = st.button("Refresh Quotes", type="primary", key="mkt_refresh_quotes")
    with c2:
        period = st.selectbox("Ingest period", ["1mo", "3mo", "6mo", "1y"], index=1, key="mkt_period", label_visibility="collapsed")
        if st.button("Trigger Ingest", key="mkt_trigger_ingest"):
            try:
                post("/v1/ingest/market", {"symbols": symbols, "period": period, "interval": "1d"})
                st.success(f"Ingest triggered for {len(symbols)} symbols ({period}).")
            except Exception as e:
                st.error(str(e))

    if refresh:
        quotes = {}
        with st.spinner("Fetching quotes…"):
            for sym in symbols:
                try:
                    quotes[sym] = get(f"/v1/stocks/{sym}/quote")
                except Exception:
                    quotes[sym] = None
        st.session_state["mkt_quotes"] = quotes
        try:
            st.session_state["mkt_regime"] = get("/v1/regime")
        except Exception:
            st.session_state["mkt_regime"] = None

    if "mkt_quotes" not in st.session_state:
        st.info("Click **Refresh Quotes** to load live market data.")
        return

    quotes = st.session_state["mkt_quotes"]

    # — Current market regime badges (R5) —
    regime_data = st.session_state.get("mkt_regime")
    if isinstance(regime_data, dict) and (regime_data.get("us") or regime_data.get("india")):
        badge_cols = st.columns(2)
        for col, (label, key) in zip(badge_cols, [("US", "us"), ("India", "india")]):
            info = regime_data.get(key)
            if not isinstance(info, dict) or not info.get("regime"):
                continue
            with col:
                st.markdown(_regime_badge(label, info["regime"], info.get("reason")), unsafe_allow_html=True)

    # — Metric cards grid —
    cols_per_row = min(len(symbols), 5)
    for chunk_start in range(0, len(symbols), cols_per_row):
        chunk = symbols[chunk_start : chunk_start + cols_per_row]
        cols = st.columns(len(chunk))
        for col, sym in zip(cols, chunk):
            q = quotes.get(sym) or {}
            price = q.get("price") or q.get("close")
            change_pct = q.get("change_pct")
            with col:
                st.markdown(_card(sym, price, change_pct), unsafe_allow_html=True)

    st.divider()

    # — OHLCV candlestick chart —
    st.subheader("Price Chart")
    col_sym, col_days, col_load = st.columns([2, 2, 1])
    with col_sym:
        selected = st.selectbox("Symbol", symbols, key="mkt_chart_sym")
    with col_days:
        chart_days = st.slider("Days", 7, 365, 60, key="mkt_chart_days")
    with col_load:
        st.write("")
        load_chart = st.button("Load Chart", key="mkt_load_chart")

    if load_chart:
        with st.spinner(f"Loading {selected} OHLCV…"):
            try:
                rows = get(f"/v1/stocks/{selected}/ohlcv", days=chart_days)
            except Exception as e:
                st.error(str(e))
                rows = []
        st.session_state["mkt_ohlcv"] = {"sym": selected, "rows": rows}

    ohlcv_state = st.session_state.get("mkt_ohlcv")
    if not ohlcv_state:
        return

    rows = ohlcv_state["rows"]
    sym_label = ohlcv_state["sym"]

    if not rows:
        st.warning(f"No OHLCV data for {sym_label}. Trigger market ingest first.")
        return

    dates = [r["timestamp"] for r in rows]
    opens  = [float(r["open"])  for r in rows]
    highs  = [float(r["high"])  for r in rows]
    lows   = [float(r["low"])   for r in rows]
    closes = [float(r["close"]) for r in rows]
    vols   = [float(r["volume"]) for r in rows]
    bar_colors = [_UP if c >= o else _DOWN for c, o in zip(closes, opens)]

    fig = go.Figure(go.Candlestick(
        x=dates, open=opens, high=highs, low=lows, close=closes,
        name=sym_label,
        increasing=dict(line=dict(color=_UP), fillcolor=_UP),
        decreasing=dict(line=dict(color=_DOWN), fillcolor=_DOWN),
    ))
    fig.update_layout(
        height=420, margin=dict(l=0, r=0, t=30, b=0),
        title=f"{sym_label} — {chart_days}d Candlestick",
        xaxis_title="Date", yaxis_title="Price ($)",
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#ccc"),
    )
    st.plotly_chart(fig, use_container_width=True)

    fig_vol = go.Figure(go.Bar(
        x=dates, y=vols, marker_color=bar_colors, name="Volume",
    ))
    fig_vol.update_layout(
        height=140, margin=dict(l=0, r=0, t=4, b=0),
        yaxis_title="Volume",
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#ccc"),
    )
    st.plotly_chart(fig_vol, use_container_width=True)
