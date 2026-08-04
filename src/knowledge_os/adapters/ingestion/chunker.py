"""Pluggable chunking strategies — fixed-size with overlap for Phase 1."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    chunk_index: int
    page: int | None
    section: str | None
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def chunk_fixed(
    text: str,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[TextChunk]:
    words = text.split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)

        page = _extract_page_marker(chunk_text)
        chunks.append(
            TextChunk(
                text=chunk_text,
                chunk_index=index,
                page=page,
                section=None,
                token_count=estimate_tokens(chunk_text),
            )
        )
        index += 1
        if end >= len(words):
            break
        start = end - overlap

    return chunks


def _extract_page_marker(text: str) -> int | None:
    if text.startswith("[Page ") and "]" in text[:12]:
        try:
            return int(text[6 : text.index("]")])
        except ValueError:
            return None
    return None
