"""Deterministic dev embeddings when external API unavailable."""

import hashlib
import math

DEV_EMBED_DIM = 384


def dev_embed(text: str, dimensions: int = DEV_EMBED_DIM) -> list[float]:
    """Hash-based pseudo-embedding for tests and offline dev."""
    digest = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    for i in range(dimensions):
        byte = digest[i % len(digest)]
        values.append((byte / 127.5) - 1.0)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
