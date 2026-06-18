import streamlit as st

from api_client import post

_SUGGESTED = [
    "What is Apple's revenue trend?",
    "Summarize the latest earnings report.",
    "What are key risk factors in recent filings?",
    "Compare gross margins across sectors.",
]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


def _fmt_source(s: dict) -> str:
    url = s.get("source_url") or ""
    doc_id = str(s.get("doc_id", "?"))[:8]
    chunk = s.get("chunk_id", s.get("chunk_index", "?"))
    score = s.get("score", 0)
    relevance = f"{float(score):.0%}"
    if url.startswith("http"):
        name = url.rstrip("/").split("/")[-1][:50] or url[:50]
        return f"[{name}]({url}) — chunk {chunk} · relevance {relevance}"
    return f"Doc `{doc_id}` — chunk {chunk} · relevance {relevance}"


def render():
    st.header("RAG Financial Assistant")
    st.caption("Ask questions about ingested financial documents. Retrieves via FAISS → Gemini generates answer.")

    # ── Suggested questions ────────────────────────────────────────────────────
    st.write("**Try asking:**")
    sug_cols = st.columns(len(_SUGGESTED))
    for col, q in zip(sug_cols, _SUGGESTED):
        if col.button(q[:32] + "…", key=f"sug_{hash(q)}", use_container_width=True):
            st.session_state["_pending_q"] = q

    col_clear, _ = st.columns([1, 6])
    with col_clear:
        if st.button("Clear Chat", key="rag_clear_chat"):
            st.session_state.chat_history = []
            st.session_state.pop("_pending_q", None)
            st.rerun()

    st.divider()

    # ── Chat history ───────────────────────────────────────────────────────────
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander(f"Sources ({len(msg['sources'])})"):
                    for s in msg["sources"]:
                        st.markdown(_fmt_source(s))

    # ── Input ──────────────────────────────────────────────────────────────────
    pending = st.session_state.pop("_pending_q", None)
    query = st.chat_input("Ask a financial question…") or pending

    if query:
        st.session_state.chat_history.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving & generating…"):
                try:
                    result = post("/v1/query", {"query": query, "top_k": 5})
                    answer = result.get("answer", "No answer returned.")
                    sources = result.get("sources", [])
                except Exception as e:
                    answer = f"⚠ Error: {e}"
                    sources = []
            st.markdown(answer)
            if sources:
                with st.expander(f"Sources ({len(sources)})"):
                    for s in sources:
                        st.markdown(_fmt_source(s))

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
        })
