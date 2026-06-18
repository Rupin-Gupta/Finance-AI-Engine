from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import get

_RATING_COLORS = {
    "buy": "green", "strong_buy": "green", "outperform": "green",
    "hold": "orange", "neutral": "orange",
    "underperform": "red", "sell": "red", "strong_sell": "red",
}


def _fmt_large(v) -> str:
    if v is None:
        return "N/A"
    v = int(v)
    if v >= 1_000_000_000_000:
        return f"${v / 1_000_000_000_000:.2f}T"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    return f"${v:,}"


def _pct(v) -> str:
    return f"{float(v) * 100:.2f}%" if v is not None else "N/A"


def _val(v, decimals=2, prefix="") -> str:
    if v is None:
        return "N/A"
    return f"{prefix}{float(v):.{decimals}f}"


def _pe_color(pe) -> str:
    if pe is None:
        return "#888"
    pe = float(pe)
    if pe < 0:
        return "#ff4444"
    if pe < 15:
        return "#00c851"
    if pe < 30:
        return "#ffa500"
    return "#ff4444"


def _days_until(d: date) -> str:
    delta = (d - date.today()).days
    if delta < 0:
        return f"{abs(delta)}d ago"
    if delta == 0:
        return "TODAY"
    return f"in {delta}d"


def render():
    st.header("Fundamental Analysis")
    symbol = st.text_input("Symbol", "AAPL", key="fund_symbol").upper().strip()

    if not st.button("Load Fundamentals", type="primary", key="fund_load_btn"):
        st.info("Enter a symbol and click **Load Fundamentals**.")
        return

    with st.spinner(f"Fetching fundamentals + quote for {symbol}…"):
        try:
            data = get(f"/v1/fundamentals/{symbol}")
        except Exception as exc:
            st.error(str(exc))
            return
        # best-effort current price
        current_price = None
        try:
            q = get(f"/v1/stocks/{symbol}/quote")
            current_price = float(q.get("price") or q.get("close") or 0) or None
        except Exception:
            pass

    if "warning" in data:
        st.warning(data["warning"])

    fund = data.get("fundamentals", {})
    earnings = data.get("earnings", [])

    # ── Row 1: headline metrics ────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Current Price", f"${current_price:.2f}" if current_price else "N/A")
    c2.metric("Market Cap", _fmt_large(fund.get("market_cap")))
    c3.metric("Analyst Target", _val(fund.get("analyst_target"), prefix="$"))

    pe = fund.get("pe_trailing")
    pe_str = _val(pe)
    pe_delta = None
    if pe is not None and current_price:
        pe_delta = f"{'Expensive' if float(pe) > 30 else 'Fair' if float(pe) > 15 else 'Cheap'}"
    c4.metric("P/E (Trailing)", pe_str, delta=pe_delta,
              delta_color="inverse" if pe and float(pe) > 30 else "normal")
    c5.metric("EPS (Trailing)", _val(fund.get("eps_trailing"), prefix="$"))

    # ── Row 2: secondary ──────────────────────────────────────────────────────
    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Beta", _val(fund.get("beta"), 3))
    c7.metric("52W High", _val(fund.get("week_52_high"), prefix="$"))
    c8.metric("52W Low", _val(fund.get("week_52_low"), prefix="$"))
    c9.metric("Dividend Yield", _pct(fund.get("dividend_yield")))

    # ── Analyst rating badge ───────────────────────────────────────────────────
    rating = (fund.get("analyst_rating") or "").lower()
    count = fund.get("analyst_count")
    color = _RATING_COLORS.get(rating, "gray")
    label = rating.replace("_", " ").upper() if rating else "N/A"
    count_str = f"({count} analysts)" if count else ""
    st.markdown(f"**Analyst Rating:** :{color}[**{label}**] {count_str}")

    # ── 52W range bar with current price ──────────────────────────────────────
    high = fund.get("week_52_high")
    low  = fund.get("week_52_low")
    target = fund.get("analyst_target")
    if high is not None and low is not None:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[float(high) - float(low)],
            base=[float(low)],
            orientation="h",
            marker_color="rgba(100,150,255,0.4)",
            name="52W Range",
            hovertemplate="Low: $%{base:.2f}<br>High: $%{x:.2f}<extra></extra>",
        ))
        if target:
            fig.add_vline(x=float(target), line_color="#ffa500", line_dash="dash",
                          annotation_text=f"Target ${float(target):.2f}",
                          annotation_position="top right")
        if current_price:
            fig.add_vline(x=current_price, line_color="#00c851", line_dash="solid",
                          annotation_text=f"Current ${current_price:.2f}",
                          annotation_position="top left")
        fig.update_layout(
            title="52-Week Price Range",
            xaxis_title="Price ($)",
            height=160, showlegend=False,
            margin=dict(t=40, b=20),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#ccc"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Valuation table ────────────────────────────────────────────────────────
    st.subheader("Valuation Metrics")
    val_data = {
        "Metric": [
            "Forward P/E", "PEG Ratio", "Price / Book",
            "Gross Margins", "Profit Margins",
            "EPS Forward", "Revenue",
        ],
        "Value": [
            _val(fund.get("pe_forward")),
            _val(fund.get("peg_ratio"), 3),
            _val(fund.get("price_to_book"), 3),
            _pct(fund.get("gross_margins")),
            _pct(fund.get("profit_margins")),
            _val(fund.get("eps_forward"), prefix="$"),
            _fmt_large(fund.get("revenue")),
        ],
    }
    st.dataframe(pd.DataFrame(val_data), use_container_width=True, hide_index=True)

    # ── Corporate Actions ──────────────────────────────────────────────────────
    st.subheader("Corporate Actions")
    try:
        actions = get(f"/v1/corporate-actions/{symbol}").get("actions", [])
    except Exception:
        actions = []
    if actions:
        st.caption("Splits/bonus adjust price history (auto-adjusted at ingest); dividends per share.")
        st.dataframe(
            pd.DataFrame([{
                "Date": a["date"],
                "Type": a["type"],
                "Ratio": a["ratio"] if a["ratio"] is not None else "—",
                "Amount": f"${a['amount']:.4f}" if a["amount"] is not None else "—",
            } for a in actions]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No corporate actions recorded — run the corporate_actions job.")

    # ── Earnings Calendar ──────────────────────────────────────────────────────
    st.subheader("Earnings Calendar")
    if not earnings:
        st.info("No earnings data available.")
        return

    df = pd.DataFrame(earnings)
    df["earnings_date"] = pd.to_datetime(df["earnings_date"]).dt.date
    df = df.sort_values("earnings_date", ascending=False)

    today = date.today()
    upcoming = df[df["earnings_date"] >= today].copy()
    past = df[df["earnings_date"] < today].copy()

    if not upcoming.empty:
        st.markdown("**Upcoming**")
        upcoming["Countdown"] = upcoming["earnings_date"].apply(_days_until)
        upcoming = upcoming.rename(columns={
            "earnings_date": "Date", "eps_estimate": "EPS Estimate",
            "eps_actual": "EPS Actual", "surprise_pct": "Surprise %",
        })
        st.dataframe(upcoming[["Date", "Countdown", "EPS Estimate", "EPS Actual", "Surprise %"]],
                     use_container_width=True, hide_index=True)

    if not past.empty:
        st.markdown("**Recent Results**")
        past = past.rename(columns={
            "earnings_date": "Date", "eps_estimate": "EPS Estimate",
            "eps_actual": "EPS Actual", "surprise_pct": "Surprise %",
        })

        def _color_surprise(val):
            if pd.isna(val):
                return ""
            return "color: #00c851" if float(val) > 0 else "color: #ff4444"

        styled = past.style.map(_color_surprise, subset=["Surprise %"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
