import streamlit as st

from api_client import get, post, delete

_REC_COLOR = {"BUY": "#00c851", "SELL": "#ff4444", "HOLD": "#888888"}
_ROW = [1.5, 1, 1, 1, 1.3, 1.3, 1.2, 1, 1, 0.8]


def _pnl_html(value, pct) -> str:
    if value is None:
        return "—"
    color = "#00c851" if value >= 0 else "#ff4444"
    sign = "+" if value >= 0 else ""
    pct_str = f" ({sign}{pct:.2%})" if pct is not None else ""
    return f"<span style='color:{color};font-weight:600'>{sign}{value:,.2f}{pct_str}</span>"


def render():
    st.header("Watchlist & Holdings")
    st.caption("Track symbols with live price, P&L, latest decision, and sentiment.")

    # ── Add / update a position ────────────────────────────────────────────────
    with st.expander("➕ Add or update a position", expanded=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            sym = st.text_input("Symbol", key="wl_symbol", placeholder="AAPL or RELIANCE.NS")
        with c2:
            qty = st.number_input("Quantity", min_value=0.0, value=0.0, step=1.0, key="wl_qty")
        with c3:
            cost = st.number_input("Cost basis", min_value=0.0, value=0.0, step=1.0, key="wl_cost")
        note = st.text_input("Note (optional)", key="wl_note")

        if st.button("Save", type="primary", key="wl_save"):
            if not sym.strip():
                st.warning("Enter a symbol.")
            else:
                body = {
                    "symbol": sym.strip().upper(),
                    "quantity": qty or None,
                    "cost_basis": cost or None,
                    "note": note.strip() or None,
                }
                try:
                    post("/v1/watchlist", body)
                    st.success(f"Saved {body['symbol']}.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # ── Load watchlist ─────────────────────────────────────────────────────────
    try:
        data = get("/v1/watchlist")
    except Exception as e:
        st.error(f"Cannot load watchlist: {e}")
        return

    if not isinstance(data, dict):
        data = {}
    items = data.get("items", [])
    totals = data.get("totals", {})

    if not items:
        st.info("Watchlist empty. Add a position above.")
        return

    # ── Portfolio totals ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Positions", totals.get("positions", 0))
    m2.metric("Market Value", f"${totals.get('market_value', 0):,.2f}")
    pnl = totals.get("unrealized_pnl", 0) or 0
    pnl_pct = totals.get("unrealized_pnl_pct")
    m3.metric("Unrealized P&L", f"${pnl:,.2f}",
              f"{pnl_pct:.2%}" if pnl_pct is not None else None)
    m4.metric("Cost Basis", f"${totals.get('cost_value', 0):,.2f}")

    st.divider()

    # ── Positions table ────────────────────────────────────────────────────────
    header = st.columns(_ROW)
    for c, label in zip(header, ["Symbol", "Qty", "Cost", "Price", "Mkt Value",
                                 "P&L", "Signal", "Size", "Sent.", ""]):
        c.markdown(f"**{label}**")

    for it in items:
        row = st.columns(_ROW)
        row[0].write(it["symbol"])
        row[1].write("—" if it["quantity"] is None else f"{it['quantity']:g}")
        row[2].write("—" if it["cost_basis"] is None else f"${it['cost_basis']:,.2f}")
        row[3].write("—" if it["current_price"] is None else f"${it['current_price']:,.2f}")
        row[4].write("—" if it["market_value"] is None else f"${it['market_value']:,.2f}")
        row[5].markdown(_pnl_html(it["unrealized_pnl"], it["unrealized_pnl_pct"]),
                        unsafe_allow_html=True)

        rec = it.get("recommendation")
        if rec:
            color = _REC_COLOR.get(rec, "#888")
            row[6].markdown(f"<span style='color:{color};font-weight:700'>{rec}</span>",
                            unsafe_allow_html=True)
        else:
            row[6].write("—")

        size = it.get("suggested_position_pct")
        row[7].write("—" if size is None else f"{size:.0%}")

        sent = it.get("sentiment_score")
        row[8].write("—" if sent is None else f"{sent:+.2f}")

        if row[9].button("✕", key=f"wl_del_{it['symbol']}", help="Remove"):
            try:
                delete(f"/v1/watchlist/{it['symbol']}")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    notes = [it for it in items if it.get("note")]
    if notes:
        with st.expander("Notes"):
            for it in notes:
                st.markdown(f"**{it['symbol']}** — {it['note']}")
