import streamlit as st

from api_client import get, post


def render():
    st.header("AI Insights")
    st.caption("LLM-generated sector & stock reports from your analytics pipeline.")

    col_gen, col_limit = st.columns([1, 2])
    with col_gen:
        if st.button("Generate New Reports", type="primary", key="reports_generate_btn"):
            with st.spinner("Running sector report generation (30–90s)…"):
                try:
                    res = post("/v1/reports/generate", {})
                    st.success(f"Generated {res.get('generated', 0)} new reports.")
                except Exception as e:
                    st.error(f"Generation failed: {e}")
    with col_limit:
        limit = st.select_slider("Show last N reports", options=[5, 10, 20, 50], value=10)

    st.divider()

    try:
        reports = get("/v1/reports", limit=limit)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")
        return

    if not reports:
        st.info("No reports yet. Click **Generate New Reports** above.")
        return

    st.caption(f"{len(reports)} reports loaded.")

    for i, report in enumerate(reports):
        created = str(report.get("created_at", ""))[:19].replace("T", " ")
        query_preview = (report.get("query") or "Report")[:80]
        with st.expander(f"📄 **{created}** — {query_preview}", expanded=(i == 0)):
            response = report.get("response", "")
            if response:
                st.markdown(response)
            else:
                st.caption("No content.")
