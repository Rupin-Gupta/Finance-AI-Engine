import pytest
from backend.rag.chunker import chunk_text, _tok


# ---------------------------------------------------------------------------
# _tok helper
# ---------------------------------------------------------------------------

def test_tok_empty():
    assert _tok("") == 1  # max(1, ...)


def test_tok_approximation():
    # 40 chars → (40+3)//4 = 10
    assert _tok("a" * 40) == 10


# ---------------------------------------------------------------------------
# Empty / whitespace guard
# ---------------------------------------------------------------------------

def test_empty_string_returns_empty():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty():
    assert chunk_text("   \n\t  ") == []


# ---------------------------------------------------------------------------
# Single chunk
# ---------------------------------------------------------------------------

def test_short_text_single_chunk():
    text = "Short sentence. Another one."
    chunks = chunk_text(text, max_tokens=400)
    assert len(chunks) == 1


def test_single_sentence_no_period_single_chunk():
    assert len(chunk_text("hello world", max_tokens=400)) == 1


# ---------------------------------------------------------------------------
# Splitting at max_tokens boundary
# ---------------------------------------------------------------------------

def test_long_text_splits_into_multiple_chunks():
    # ~2000 chars → many token-sized pieces
    text = ". ".join(["word " * 20] * 20)
    chunks = chunk_text(text, max_tokens=50)
    assert len(chunks) > 1


def test_all_chunks_non_empty():
    text = ". ".join(["word " * 20] * 30)
    chunks = chunk_text(text, max_tokens=50)
    assert all(c.strip() for c in chunks)


def test_long_delimiterless_text_splits():
    # word soup with no ". " delimiters → goes through split_long_sentence
    text = " ".join(["word"] * 1000)
    chunks = chunk_text(text, max_tokens=100)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


# ---------------------------------------------------------------------------
# Overlap — later chunks must share content with earlier ones
# ---------------------------------------------------------------------------

def test_overlap_carries_context():
    # Build text with distinct labelled sentences
    sentences = [f"Sentence number {i} about topic alpha beta." for i in range(40)]
    text = " ".join(sentences)
    chunks = chunk_text(text, max_tokens=80, overlap=30)
    assert len(chunks) > 1
    # At least one word from chunk N must appear in chunk N+1
    for a, b in zip(chunks, chunks[1:]):
        words_a = set(a.split())
        words_b = set(b.split())
        assert words_a & words_b, "Adjacent chunks share no tokens — overlap broken"


# ---------------------------------------------------------------------------
# Unicode / multibyte
# ---------------------------------------------------------------------------

def test_unicode_text_does_not_crash():
    text = "Résultats financiers. Ingresos netos aumentaron. 収益が増加しました。"
    chunks = chunk_text(text, max_tokens=20)
    assert isinstance(chunks, list)
    assert all(isinstance(c, str) for c in chunks)


def test_unicode_chunks_non_empty():
    text = ". ".join(["αβγδεζηθ " * 10] * 15)
    chunks = chunk_text(text, max_tokens=40)
    assert all(c.strip() for c in chunks)


# ---------------------------------------------------------------------------
# Edge: single sentence longer than max_tokens → forced split
# ---------------------------------------------------------------------------

def test_single_very_long_sentence_splits():
    long_sentence = "word " * 500  # no ". " delimiter
    chunks = chunk_text(long_sentence, max_tokens=50)
    assert len(chunks) > 1


def test_single_long_sentence_chunks_bounded():
    long_sentence = "tok " * 800
    chunks = chunk_text(long_sentence, max_tokens=100)
    # Every chunk token estimate should be ≤ max_tokens * 4 chars
    for c in chunks:
        assert len(c) <= 100 * 4 * 6  # generous upper bound


# ---------------------------------------------------------------------------
# max_tokens param respected
# ---------------------------------------------------------------------------

def test_small_max_tokens_produces_more_chunks():
    text = ". ".join(["The quick brown fox jumps over the lazy dog"] * 20)
    chunks_small = chunk_text(text, max_tokens=20)
    chunks_large = chunk_text(text, max_tokens=200)
    assert len(chunks_small) >= len(chunks_large)
