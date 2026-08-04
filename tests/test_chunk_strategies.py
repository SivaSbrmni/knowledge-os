from knowledge_os.adapters.ingestion.strategies import chunk_structure_aware


def test_structure_aware_splits_pages():
    text = "[Page 1]\nIntro text here.\n\n[Page 2]\nSecond page content."
    chunks = chunk_structure_aware(text, chunk_size=50, overlap=5)
    assert len(chunks) >= 2
    assert any(c.page == 1 for c in chunks)
    assert any(c.page == 2 for c in chunks)
