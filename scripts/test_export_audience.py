import io

from scripts.export_audience import segment_where, write_csv


def test_segment_where_clauses():
    assert segment_where("all") == ""
    assert "email_verified_at IS NOT NULL" in segment_where("verified")
    assert "marketing_opt_in" in segment_where("opted-in")
    assert "has_strategy" in segment_where("engaged")


def test_write_csv_emits_header_and_rows():
    buf = io.StringIO()
    write_csv(buf, [{"email": "a@b.com", "tier": "free", "verified": True,
                     "opted_in": False, "has_strategy": True, "has_traded": False,
                     "has_backtest": False, "has_progress": False}])
    out = buf.getvalue()
    assert out.splitlines()[0].startswith("email,tier,verified")
    assert "a@b.com" in out
