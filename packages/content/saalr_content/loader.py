from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass

_REQUIRED = {"slug", "title", "summary", "order", "min_tier", "est_minutes"}
_VALID_TIERS = {"free", "pro"}
_WS = re.compile(r"\s+")


class ContentError(Exception):
    """A module's frontmatter/body is malformed, or the catalog is inconsistent."""


@dataclass(frozen=True)
class Module:
    slug: str
    title: str
    summary: str
    order: int
    min_tier: str
    est_minutes: int
    body: str


@dataclass(frozen=True)
class SearchHit:
    module: Module
    score: int
    snippet: str


def parse_module(text: str, name: str) -> Module:
    if not text.startswith("---"):
        raise ContentError(f"{name}: missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ContentError(f"{name}: malformed frontmatter fences")
    fm_raw, body = parts[1], parts[2]
    fm: dict[str, str] = {}
    for line in fm_raw.strip().splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ContentError(f"{name}: bad frontmatter line {line!r}")
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"')
    keys = set(fm)
    if keys != _REQUIRED:
        raise ContentError(f"{name}: frontmatter keys {sorted(keys)} != {sorted(_REQUIRED)}")
    if fm["min_tier"] not in _VALID_TIERS:
        raise ContentError(f"{name}: min_tier must be free|pro, got {fm['min_tier']!r}")
    try:
        order = int(fm["order"])
        est = int(fm["est_minutes"])
    except ValueError as exc:
        raise ContentError(f"{name}: order/est_minutes must be integers") from exc
    return Module(fm["slug"], fm["title"], fm["summary"], order, fm["min_tier"], est, body.strip())


def _snippet(module: Module, ql: str) -> str:
    body = module.body
    idx = body.lower().find(ql)
    if idx < 0:
        return _WS.sub(" ", module.summary).strip()[:160]
    start = max(0, idx - 60)
    return _WS.sub(" ", body[start:start + 160]).strip()


@dataclass
class Catalog:
    modules: list[Module]

    def __post_init__(self) -> None:
        # a Catalog is always presented in course order (then slug, for stable ties)
        self.modules = sorted(self.modules, key=lambda m: (m.order, m.slug))

    @staticmethod
    def validate_unique(modules: list[Module]) -> list[Module]:
        seen: set[str] = set()
        for m in modules:
            if m.slug in seen:
                raise ContentError(f"duplicate slug {m.slug!r}")
            seen.add(m.slug)
        return modules

    def by_slug(self, slug: str) -> Module | None:
        return next((m for m in self.modules if m.slug == slug), None)

    def search(self, q: str) -> list[SearchHit]:
        ql = q.lower().strip()
        if not ql:
            return []
        scored: list[tuple[tuple[int, int, int, int], SearchHit]] = []
        for m in self.modules:
            tc = m.title.lower().count(ql)
            sc = m.summary.lower().count(ql)
            bc = m.body.lower().count(ql)
            if tc + sc + bc == 0:
                continue
            display = tc * 3 + sc * 2 + bc
            # rank so ANY title hit outranks summary-only, which outranks body-only;
            # ties broken by course order (-order, so lower order sorts first under reverse).
            scored.append(((tc, sc, bc, -m.order), SearchHit(m, display, _snippet(m, ql))))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [hit for _, hit in scored]


def load_catalog() -> Catalog:
    """Parse every bundled markdown module into a Catalog (sorted by order, then slug)."""
    root = importlib.resources.files("saalr_content").joinpath("modules")
    modules: list[Module] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".md"):
            modules.append(parse_module(entry.read_text(encoding="utf-8"), entry.name))
    Catalog.validate_unique(modules)
    return Catalog(modules)
