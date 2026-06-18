import pandas as pd
import streamlit as st

from api_client import get


def render():
    st.header("Options Chain")
    st.caption("Live calls & puts via yfinance. Strike, bid/ask, IV, volume, open interest.")

    col1, col2 = st.columns([2, 1])
    with col1:
        symbol = st.text_input("Symbol", "AAPL", key="options_symbol").upper().strip()
    with col2:
        expiry_input = st.text_input(
            "Expiry (optional)", "",
            key="options_expiry",
            help="YYYY-MM-DD. Leave blank for nearest expiry.",
        ).strip()

    if not st.button("Load Options Chain", key="options_load"):
        return

    params = {}
    if expiry_input:
        params["expiry"] = expiry_input

    with st.spinner(f"Fetching options for {symbol}..."):
        try:
            data = get(f"/v1/options/{symbol}", **params)
        except Exception as exc:
            st.error(f"API error: {exc}")
            return

    if not data:
        st.warning("No options data returned.")
        return

    selected = data.get("expiry", "")
    expiries = data.get("expiries", [])
    calls = data.get("calls", [])
    puts = data.get("puts", [])

    st.caption(f"Expiry: **{selected}** — {len(expiries)} expirations available")

    if len(expiries) > 1:
        preview = expiries[:10]
        st.write("Available expiries: " + "  ·  ".join(preview) + ("  ·  …" if len(expiries) > 10 else ""))

    tab_calls, tab_puts = st.tabs([f"Calls ({len(calls)})", f"Puts ({len(puts)})"])

    with tab_calls:
        _render_chain(calls, "calls")
    with tab_puts:
        _render_chain(puts, "puts")


def _render_chain(rows: list, label: str) -> None:
    if not rows:
        st.info(f"No {label} data available.")
        return

    df = pd.DataFrame(rows)

    col_map = {
        "strike": "Strike",
        "lastPrice": "Last",
        "bid": "Bid",
        "ask": "Ask",
        "volume": "Volume",
        "openInterest": "OI",
        "impliedVolatility": "IV",
        "inTheMoney": "ITM",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    for col in ["Strike", "Last", "Bid", "Ask"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"${x:.2f}" if x is not None else "—")

    for col in ["Volume", "OI"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{int(x):,}" if x is not None else "—")

    if "IV" in df.columns:
        df["IV"] = df["IV"].apply(lambda x: f"{x:.1%}" if x is not None else "—")

    st.dataframe(df, use_container_width=True, hide_index=True)

    itm_count = sum(1 for r in rows if r.get("inTheMoney"))
    st.caption(f"{len(rows)} contracts · {itm_count} in-the-money")
