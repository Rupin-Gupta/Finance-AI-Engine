import plotly.graph_objects as go
import streamlit as st

from api_client import get, post

_PLOT = dict(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#ccc"))


def _pnl_md(v) -> str:
    if v is None:
        return "—"
    color = "#00c851" if v >= 0 else "#ff4444"
    return f"<span style='color:{color};font-weight:600'>{v:+,.2f}</span>"


def render():
    st.header("Paper Trading")
    st.caption("Virtual portfolio executed against the latest real prices (with realistic costs). "
               "Prove the engine's edge before risking capital.")

    try:
        data = get("/v1/paper")
    except Exception as e:
        st.error(f"Cannot load portfolio: {e}")
        return

    if not isinstance(data, dict):
        data = {}
    m = data.get("metrics", {})
    positions = data.get("positions", [])

    # ── Portfolio summary ──────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity", f"${m.get('equity', 0):,.2f}")
    tr = m.get("total_return")
    c2.metric("Total Return", f"{tr:+.2%}" if tr is not None else "—")
    c3.metric("Cash", f"${m.get('cash', 0):,.2f}")
    c4.metric("Positions Value", f"${m.get('positions_value', 0):,.2f}")
    c5.metric("Unrealized P&L", f"${m.get('unrealized_pnl', 0):,.2f}")
    st.caption(f"Starting capital: ${m.get('starting_cash', 0):,.0f}")

    # ── Trade form ─────────────────────────────────────────────────────────────
    st.subheader("Place a Trade")
    t1, t2, t3, t4 = st.columns([2, 1, 1, 1])
    with t1:
        sym = st.text_input("Symbol", key="paper_sym", placeholder="AAPL or RELIANCE.NS")
    with t2:
        side = st.selectbox("Side", ["BUY", "SELL"], key="paper_side")
    with t3:
        qty = st.number_input("Quantity", min_value=0.0, value=1.0, step=1.0, key="paper_qty")
    with t4:
        st.write("")
        st.write("")
        go_trade = st.button("Execute", type="primary", key="paper_exec")

    if go_trade:
        if not sym.strip() or qty <= 0:
            st.warning("Enter a symbol and a positive quantity.")
        else:
            try:
                res = post("/v1/paper/trade",
                           {"symbol": sym.strip().upper(), "side": side, "quantity": qty})
                tr_ = res["trade"]
                msg = f"{tr_['side']} {tr_['quantity']:g} {tr_['symbol']} @ ${tr_['price']:.2f} (fee ${tr_['fee']:.2f})"
                if tr_.get("realized_pnl") is not None:
                    msg += f" · realized P&L ${tr_['realized_pnl']:+.2f}"
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    # ── Positions ──────────────────────────────────────────────────────────────
    st.subheader("Positions")
    if not positions:
        st.info("No open positions. Place a BUY above.")
    else:
        header = st.columns([1.5, 1, 1.2, 1.2, 1.4, 1.4])
        for c, h in zip(header, ["Symbol", "Qty", "Avg Cost", "Price", "Mkt Value", "Unrealized"]):
            c.markdown(f"**{h}**")
        for p in positions:
            row = st.columns([1.5, 1, 1.2, 1.2, 1.4, 1.4])
            row[0].write(p["symbol"])
            row[1].write(f"{p['quantity']:g}")
            row[2].write(f"${p['avg_cost']:,.2f}")
            row[3].write("—" if p["current_price"] is None else f"${p['current_price']:,.2f}")
            row[4].write("—" if p["market_value"] is None else f"${p['market_value']:,.2f}")
            row[5].markdown(_pnl_md(p["unrealized_pnl"]), unsafe_allow_html=True)

    # ── Equity curve + over-time metrics (R1.2) ────────────────────────────────
    try:
        hist = get("/v1/paper/history")
    except Exception:
        hist = {}
    curve = (hist or {}).get("curve", [])
    hm = (hist or {}).get("metrics", {})
    if curve:
        st.subheader("Equity Curve")
        e1, e2, e3, e4 = st.columns(4)
        sh = hm.get("sharpe")
        dd = hm.get("max_drawdown")
        wr = hm.get("win_rate")
        tr2 = hm.get("total_return")
        e1.metric("Sharpe (ann.)", f"{sh:.2f}" if sh is not None else "—")
        e2.metric("Max Drawdown", f"{dd:.2%}" if dd is not None else "—")
        e3.metric("Win Rate", f"{wr:.0%}" if wr is not None else "—")
        e4.metric("Return (curve)", f"{tr2:+.2%}" if tr2 is not None else "—")
        fig = go.Figure(go.Scatter(
            x=[p["ts"][:19] for p in curve], y=[p["equity"] for p in curve],
            mode="lines", line=dict(color="#7eb8f7"), fill="tozeroy",
        ))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="Equity ($)", **_PLOT)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Equity curve builds once the paper auto-run job records snapshots "
                   "(enable PAPER_AUTO_TRADE_ENABLED or trigger paper_auto_run).")

    # ── Trade log ──────────────────────────────────────────────────────────────
    with st.expander("Trade log"):
        try:
            trades = get("/v1/paper/trades").get("trades", [])
        except Exception:
            trades = []
        if trades:
            st.dataframe(
                [{
                    "Time": t["ts"][:19], "Symbol": t["symbol"], "Side": t["side"],
                    "Qty": t["quantity"], "Price": round(t["price"], 2), "Fee": round(t["fee"], 2),
                    "Realized P&L": t["realized_pnl"],
                } for t in trades],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("No trades yet.")

    # ── Reset ──────────────────────────────────────────────────────────────────
    with st.expander("⚙ Reset portfolio"):
        new_cash = st.number_input("Starting cash", min_value=1000.0, value=100_000.0,
                                   step=10_000.0, key="paper_reset_cash")
        if st.button("Reset (clears positions + trades)", key="paper_reset_btn"):
            try:
                post("/v1/paper/reset", {"starting_cash": new_cash})
                st.success("Portfolio reset.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
