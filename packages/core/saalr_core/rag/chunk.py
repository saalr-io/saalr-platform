from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    module_slug: str
    chunk_index: int
    content: str


def chunk_module(module) -> list[Chunk]:
    """One chunk per module for now (modules are short). The seam for future paragraph chunking."""
    content = f"{module.title}\n\n{module.summary}\n\n{module.body}"
    return [Chunk(module.slug, 0, content)]
