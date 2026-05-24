import streamlit as st

st.set_page_config(page_title="Financial AI Platform", layout="wide")

from page_modules import market_overview, analytics, ai_insights, rag_chat, jobs, data_upload, decision_intelligence

TABS = {
    "Market Overview": market_overview.render,
    "Analytics": analytics.render,
    "AI Insights": ai_insights.render,
    "Decision Intelligence": decision_intelligence.render,
    "RAG Chat": rag_chat.render,
    "Knowledge Base": data_upload.render,
    "Jobs": jobs.render,
}

tab_names = list(TABS.keys())
tabs = st.tabs(tab_names)

for tab, (name, render_fn) in zip(tabs, TABS.items()):
    with tab:
        render_fn()
