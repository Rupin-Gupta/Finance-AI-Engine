import streamlit as st
from api_client import get


def render():
    st.header("Background Jobs")
    job_id = st.text_input("Job ID")
    if st.button("Lookup") and job_id:
        try:
            job = get(f"/v1/jobs/{job_id.strip()}")
            st.json(job)
        except Exception as e:
            st.error(str(e))
