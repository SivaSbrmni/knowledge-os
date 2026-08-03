from knowledge_os.adapters.ingestion.chunker import chunk_fixed, estimate_tokens


def test_chunk_fixed_produces_overlapping_chunks():
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_fixed(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(c.token_count > 0 for c in chunks)
    assert chunks[0].chunk_index == 0


def test_estimate_tokens():
    assert estimate_tokens("one two three") == 3


def test_chunk_empty_text():
    assert chunk_fixed("") == []
