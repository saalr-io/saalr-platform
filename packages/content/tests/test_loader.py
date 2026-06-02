import pytest

from saalr_content.loader import Catalog, ContentError, Module, load_catalog, parse_module


def _md(slug="x", title="T", summary="S", order=10, min_tier="free", est=5, body="Body here."):
    return (f"---\nslug: {slug}\ntitle: \"{title}\"\nsummary: {summary}\n"
            f"order: {order}\nmin_tier: {min_tier}\nest_minutes: {est}\n---\n{body}\n")


def test_parse_module_reads_frontmatter_and_body():
    m = parse_module(_md(slug="abc", title="Hi", order=3, est=9, body="# Heading\ntext"), "abc.md")
    assert isinstance(m, Module)
    assert m.slug == "abc" and m.title == "Hi" and m.order == 3 and m.est_minutes == 9
    assert m.min_tier == "free" and m.body.startswith("# Heading")


def test_missing_key_raises():
    bad = "---\nslug: a\ntitle: T\n---\nbody"
    with pytest.raises(ContentError):
        parse_module(bad, "a.md")


def test_bad_min_tier_raises():
    with pytest.raises(ContentError):
        parse_module(_md(min_tier="enterprise"), "a.md")


def test_non_int_order_raises():
    with pytest.raises(ContentError):
        parse_module(_md(order="soon"), "a.md")


def test_catalog_sorts_by_order_and_search_ranks_title_over_body():
    a = parse_module(_md(slug="a", title="Theta basics", order=20, body="about decay"), "a.md")
    b = parse_module(_md(slug="b", title="Intro", order=10, body="theta theta theta"), "b.md")
    cat = Catalog([a, b])
    assert [m.slug for m in cat.modules] == ["b", "a"]  # sorted by order
    hits = cat.search("theta")
    assert hits[0].module.slug == "a"  # title hit outranks 3 body hits
    assert all(h.score > 0 for h in hits) and hits[0].snippet


def test_search_blank_returns_nothing_meaningful_and_excludes_zero():
    cat = Catalog([parse_module(_md(slug="a", title="X", body="y"), "a.md")])
    assert cat.search("zzz") == []


def test_duplicate_slug_raises():
    with pytest.raises(ContentError):
        Catalog.validate_unique([parse_module(_md(slug="dup"), "1.md"),
                                 parse_module(_md(slug="dup"), "2.md")])


def test_real_catalog_loads():
    cat = load_catalog()
    assert len(cat.modules) >= 6
    assert all(m.min_tier in ("free", "pro") for m in cat.modules)
    assert cat.by_slug("iron-condor-construction").min_tier == "pro"
    assert cat.by_slug("nope") is None
