import streamlit as st

from api_client import get, post

_NAMED_JOBS = [
    ("market_refresh",  "Market Refresh",  "Fetch OHLCV for all symbols"),
    ("analytics_run",   "Analytics Run",   "Compute SMA/EMA/RSI/Volatility/Momentum"),
    ("anomaly_scan",    "Anomaly Scan",    "Z-score + IsoForest detection"),
    ("sentiment_run",   "Sentiment Run",   "6-source social & news sentiment"),
    ("decision_run",    "Decision Run",    "BUY/SELL/HOLD for all symbols"),
    ("report_run",      "Report Run",      "LLM sector report generation"),
]

_STATUS_COLOR = {
    "running":   "#ffa500",
    "completed": "#00c851",
    "failed":    "#ff4444",
}


def render():
    st.header("Background Jobs")

    # ── Trigger section ────────────────────────────────────────────────────────
    st.subheader("Trigger Jobs")
    st.caption("Fire any job immediately. Runs in background — returns 202 Accepted.")
    cols = st.columns(3)
    for i, (key, label, desc) in enumerate(_NAMED_JOBS):
        with cols[i % 3]:
            if st.button(label, key=f"trigger_{key}", help=desc, use_container_width=True):
                try:
                    post(f"/v1/jobs/trigger/{key}", {})
                    st.success(f"{label} triggered.")
                except Exception as e:
                    st.error(str(e))

    st.divider()

    # ── Recent jobs table ──────────────────────────────────────────────────────
    st.subheader("Recent Jobs")
    col_r, _ = st.columns([1, 5])
    with col_r:
        if st.button("↺ Refresh", key="jobs_refresh"):
            pass  # re-render fetches fresh data

    try:
        jobs = get("/v1/jobs", limit=30)
    except Exception as e:
        st.error(f"Cannot load jobs: {e}")
        return

    if not jobs:
        st.info("No jobs recorded yet. Trigger one above.")
        return

    header = st.columns([2, 1, 2, 2, 1])
    for h, label in zip(header, ["Job", "Status", "Started", "Finished", "ID"]):
        h.markdown(f"**{label}**")

    for job in jobs:
        status = job.get("status", "unknown")
        color  = _STATUS_COLOR.get(status, "#888")
        started  = str(job.get("started_at",  "") or "")[:19].replace("T", " ")
        finished = str(job.get("finished_at", "") or "")[:19].replace("T", " ") or "—"
        job_id   = str(job.get("id", ""))[:8]
        job_type = job.get("type", "unknown")
        error    = job.get("error") or ""

        row = st.columns([2, 1, 2, 2, 1])
        row[0].write(job_type)
        row[1].markdown(f"<span style='color:{color}'>● {status}</span>", unsafe_allow_html=True)
        row[2].write(started)
        row[3].write(finished)
        row[4].code(job_id, language=None)

        if error:
            with st.expander(f"⚠ Error — {job_type}"):
                st.error(error)

    st.divider()

    # ── Job lookup by ID ───────────────────────────────────────────────────────
    st.subheader("Lookup by Job ID")
    job_id_input = st.text_input("Full Job UUID", key="job_lookup_id", placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
    if st.button("Lookup", key="job_lookup_btn") and job_id_input.strip():
        try:
            st.json(get(f"/v1/jobs/{job_id_input.strip()}"))
        except Exception as e:
            st.error(str(e))
