def _tok(text: str) -> int:
    """Approximate token count: 1 token ≈ 4 chars (standard heuristic)."""
    return max(1, (len(text) + 3) // 4)


def chunk_text(text: str, max_tokens: int = 400, overlap: int = 50) -> list[str]:
    """Sentence-aware chunker with token overlap."""
    if not text or not text.strip():
        return []

    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    count = 0

    def flush_current() -> None:
        if current:
            chunks.append(". ".join(current) + ".")

    def split_long_sentence(sentence: str) -> None:
        words = sentence.split()
        if not words:
            return
        # word-level fallback for single sentences longer than max_tokens
        overlap_words = min(overlap * 4, (max_tokens - 1) * 4)
        step = max(1, max_tokens * 4 - overlap_words)
        start = 0
        while start < len(words):
            chunk_words = words[start:start + max_tokens * 4]
            chunks.append(" ".join(chunk_words) + ".")
            if start + max_tokens * 4 >= len(words):
                break
            start += step

    for sent in sentences:
        sent_toks = _tok(sent)
        if sent_toks > max_tokens:
            flush_current()
            current, count = [], 0
            split_long_sentence(sent)
            continue
        if count + sent_toks > max_tokens and current:
            flush_current()
            # carry over trailing sentences until they fill ~overlap tokens
            overlap_sentences: list[str] = []
            kept = 0
            for s in reversed(current):
                w = _tok(s)
                if kept + w > overlap:
                    break
                overlap_sentences.insert(0, s)
                kept += w
            current = overlap_sentences
            count = sum(_tok(s) for s in current)
        current.append(sent)
        count += sent_toks

    if current:
        chunks.append(". ".join(current) + ".")
    return chunks
