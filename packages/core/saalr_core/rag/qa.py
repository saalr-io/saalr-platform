from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from saalr_core.db.models.content import ContentEmbedding


@dataclass(frozen=True)
class RetrievedChunk:
    module_slug: str
    content: str
    distance: float


async def retrieve_context(session, query_vector, *, model: str, k: int) -> list[RetrievedChunk]:
    """Top-k chunks (with their text) for the question vector, ascending by cosine distance."""
    distance = ContentEmbedding.embedding.cosine_distance(query_vector)
    rows = (await session.execute(
        select(ContentEmbedding.module_slug, ContentEmbedding.content, distance.label("distance"))
        .where(ContentEmbedding.embedding_model == model)
        .order_by(distance)
        .limit(k)
    )).all()
    return [RetrievedChunk(r.module_slug, r.content, float(r.distance)) for r in rows]


_SYSTEM = (
    "You are the OptionsAcademy assistant. Answer the user's question using ONLY the numbered "
    "excerpts provided. Be concise and educational. If the excerpts do not cover the question, "
    "say you don't have material on that topic. Do not invent facts."
)


def build_qa_prompt(question: str, chunks: list[RetrievedChunk]) -> tuple[str, str]:
    """Pure: assemble the (system, user) messages grounding the answer in the retrieved excerpts."""
    lines = [f"Question: {question}", "", "Excerpts:"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[{i}] ({chunk.module_slug})\n{chunk.content}")
    return _SYSTEM, "\n".join(lines)
