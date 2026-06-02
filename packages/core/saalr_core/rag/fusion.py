from __future__ import annotations


def reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
    """Fuse ranked key-lists by Reciprocal Rank Fusion: score(key) = sum 1/(k + rank).

    No score normalization needed. Returns (key, score) sorted by score desc, ties broken by
    first appearance (stable).
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    seq = 0
    for lst in ranked_lists:
        for rank, key in enumerate(lst):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in first_seen:
                first_seen[key] = seq
                seq += 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
