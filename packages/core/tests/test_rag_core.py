import math

from saalr_core.rag.chunk import Chunk, chunk_module
from saalr_core.rag.embeddings import HashEmbeddingProvider, make_embedding_provider
from saalr_core.rag.fusion import reciprocal_rank_fusion


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class _Mod:
    def __init__(self, slug, title, summary, body):
        self.slug, self.title, self.summary, self.body = slug, title, summary, body


async def test_hash_provider_is_deterministic_and_right_dim():
    p = HashEmbeddingProvider(dim=64)
    a1, = await p.embed(["theta time decay"])
    a2, = await p.embed(["theta time decay"])
    assert a1 == a2 and len(a1) == 64
    assert abs(math.sqrt(sum(x * x for x in a1)) - 1.0) < 1e-9  # L2-normalized


async def test_hash_overlap_more_similar_than_disjoint():
    p = HashEmbeddingProvider(dim=256)
    theta_long, theta_short, iv = await p.embed(
        ["theta time decay erosion", "theta decay", "implied volatility crush"])
    assert _cos(theta_long, theta_short) > _cos(theta_long, iv)


async def test_empty_text_is_zero_vector():
    p = HashEmbeddingProvider(dim=16)
    v, = await p.embed([""])
    assert v == [0.0] * 16


def test_make_provider_none_without_key():
    class _S:
        openai_api_key = None
        embedding_model = "text-embedding-3-small"
    assert make_embedding_provider(_S()) is None


def test_make_provider_openai_with_key():
    from saalr_core.rag.embeddings import EmbeddingProvider

    class _S:
        openai_api_key = "sk-test"
        embedding_model = "text-embedding-3-small"
    p = make_embedding_provider(_S())
    assert p is not None and isinstance(p, EmbeddingProvider)  # structural Protocol check
    assert p.model_name == "text-embedding-3-small" and p.dim == 1536


def test_chunk_module_one_chunk():
    m = _Mod("greeks-delta", "The Greeks: Delta", "Delta summary", "Body about delta.")
    chunks = chunk_module(m)
    assert len(chunks) == 1
    c = chunks[0]
    assert isinstance(c, Chunk) and c.module_slug == "greeks-delta" and c.chunk_index == 0
    assert "The Greeks: Delta" in c.content and "Body about delta." in c.content


def test_rrf_fuses_and_ranks_overlap_first():
    # 'b' appears high in both lists -> should win; ties stable by first appearance
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "a"]])
    keys = [k for k, _ in fused]
    assert keys[0] == "b"
    assert set(keys) == {"a", "b", "c", "d"}


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == []
