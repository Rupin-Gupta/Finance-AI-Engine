import streamlit as st
from api_client import get


def render():
    st.header("Market Overview")
    symbols = st.text_input("Symbols (comma-separated)", "AAPL,MSFT,GOOGL").upper().split(",")
    if st.button("Refresh Quotes"):
        cols = st.columns(len(symbols))
        for col, sym in zip(cols, symbols):
            sym = sym.strip()
            try:
                data = get(f"/v1/stocks/{sym}/quote")
                col.metric(sym, f"${data.get('price', 'N/A')}", f"{data.get('change_pct', 0):.2f}%")
            except Exception as e:
                col.error(str(e))
