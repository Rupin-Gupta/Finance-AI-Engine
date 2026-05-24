import streamlit as st
from api_client import get


def render():
    st.header("AI Insights")
    try:
        data = get("/v1/reports", limit=10)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")
        return
    if not data:
        st.info("No reports yet.")
        return
    for report in data:
        with st.expander(f"{report.get('created_at', '')} — {report.get('query', '')[:60]}"):
            st.write(report.get("response", ""))
