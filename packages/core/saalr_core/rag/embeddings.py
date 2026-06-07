from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"\w+")


class EmbeddingError(Exception):
    """Wraps an embedding provider/transport failure (never carries the API key)."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector (length `dim`) per input text."""
        ...


class HashEmbeddingProvider:
    """Deterministic, network-free embedder for tests: bag-of-words token hashing,
    L2-normalized. Shared tokens -> shared dims -> high cosine; disjoint -> ~orthogonal."""

    model_name = "hash-v1"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big") % self.dim
            vec[h] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbeddingProvider:
    """OpenAI embeddings. `openai` is imported lazily, so importing this module needs no SDK."""

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small", dim: int = 1536) -> None:
        self._api_key = api_key
        self.model_name = model_name
        self.dim = dim
        self._client = None  # lazily built once (reuses the SDK's connection pool)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise EmbeddingError("openai not installed (pip install openai)") from exc
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key)
        try:
            resp = await self._client.embeddings.create(model=self.model_name, input=texts)
        except Exception as exc:
            # Keep the message generic so a provider response body never leaks (incl. the key).
            raise EmbeddingError(f"openai embedding failed ({type(exc).__name__})") from exc
        return [d.embedding for d in resp.data]


def make_embedding_provider(settings) -> EmbeddingProvider | None:
    """OpenAI provider if a key is configured, else None (search degrades to keyword)."""
    if settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.embedding_model)
    return None
