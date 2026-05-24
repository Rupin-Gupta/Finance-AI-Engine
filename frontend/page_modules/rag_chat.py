import streamlit as st
from api_client import post

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


def render():
    st.header("RAG Financial Assistant")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("sources"):
                with st.expander("Sources"):
                    for s in msg["sources"]:
                        st.write(f"doc={s['doc_id']} chunk={s['chunk_id']} score={s['score']:.3f}")

    query = st.chat_input("Ask a financial question…")
    if query:
        st.session_state.chat_history.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.write(query)
        with st.chat_message("assistant"):
            with st.spinner("Retrieving…"):
                result = post("/v1/query", {"query": query, "top_k": 5})
            st.write(result["answer"])
            if result.get("sources"):
                with st.expander("Sources"):
                    for s in result["sources"]:
                        st.write(f"doc={s['doc_id']} chunk={s['chunk_id']} score={s['score']:.3f}")
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result.get("sources", []),
        })
