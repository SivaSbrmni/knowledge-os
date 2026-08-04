"""Pluggable chunking strategies."""

import re
from collections.abc import Callable

from knowledge_os.adapters.ingestion.chunker import TextChunk, chunk_fixed, estimate_tokens

ChunkStrategy = Callable[[str], list[TextChunk]]


def chunk_structure_aware(text: str, *, chunk_size: int = 500, overlap: int = 50) -> list[TextChunk]:
    """Split by page markers and headings before fixed-size fallback."""
    sections = re.split(r"(?=\[Page \d+\])", text)
    chunks: list[TextChunk] = []
    index = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        page = None
        if section.startswith("[Page "):
            try:
                page = int(section[6:section.index("]")])
            except ValueError:
                page = None
        sub_chunks = chunk_fixed(section, chunk_size=chunk_size, overlap=overlap)
        for sc in sub_chunks:
            chunks.append(
                TextChunk(
                    text=sc.text,
                    chunk_index=index,
                    page=page or sc.page,
                    section=sc.section,
                    token_count=estimate_tokens(sc.text),
                )
            )
            index += 1
    return chunks if chunks else chunk_fixed(text, chunk_size=chunk_size, overlap=overlap)


STRATEGIES: dict[str, ChunkStrategy] = {
    "fixed": chunk_fixed,
    "structure_aware": chunk_structure_aware,
}


def get_chunk_strategy(name: str) -> ChunkStrategy:
    return STRATEGIES.get(name, chunk_fixed)
