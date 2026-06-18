import streamlit as st
from api_client import upload_file

DOC_TYPES = {
    "Earnings Report": "earnings_report",
    "Annual Report (10-K)": "10-K",
    "Quarterly Report (10-Q)": "10-Q",
    "Financial News": "news",
    "Analyst Summary": "analyst_summary",
    "Stock Performance Summary": "stock_summary",
    "Company Overview": "company_overview",
    "Other": "report",
}

ACCEPTED = ["pdf", "txt", "md", "csv", "xlsx", "xls", "json", "html"]


def render():
    st.header("Knowledge Base Upload")
    st.caption("Upload financial documents to power the RAG assistant.")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Upload by File")
        doc_type_label = st.selectbox("Document Type", list(DOC_TYPES.keys()))
        doc_type = DOC_TYPES[doc_type_label]
        files = st.file_uploader(
            "Choose files",
            accept_multiple_files=True,
            type=ACCEPTED,
            help="Supported: PDF, TXT, MD, CSV, XLSX, JSON, HTML",
        )
        if st.button("Upload & Ingest", disabled=not files, key="data_upload_ingest"):
            for f in files:
                with st.spinner(f"Ingesting {f.name}…"):
                    try:
                        result = upload_file("/v1/ingest/upload", f, doc_type)
                        st.success(f"✓ {f.name} — job `{result['job_id']}`")
                    except Exception as e:
                        st.error(f"✗ {f.name}: {e}")

    with col2:
        st.subheader("Upload by URL")
        url = st.text_input("Document URL", placeholder="https://…")
        url_doc_type_label = st.selectbox("Type", list(DOC_TYPES.keys()), key="url_type")
        url_doc_type = DOC_TYPES[url_doc_type_label]
        if st.button("Fetch & Ingest", disabled=not url, key="data_fetch_ingest"):
            with st.spinner("Fetching & ingesting…"):
                try:
                    from api_client import post
                    result = post("/v1/ingest/docs", {"source_url": url, "doc_type": url_doc_type})
                    st.success(f"✓ Job `{result['job_id']}`")
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.subheader("Ingested Documents")
    try:
        from api_client import get
        docs = get("/v1/reports/docs")
        if not docs:
            st.info("No documents ingested yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(docs)[["source_url", "doc_type", "chunk_count", "ingested_at"]]
            df.columns = ["Source", "Type", "Chunks", "Ingested At"]
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load doc list: {e}")
