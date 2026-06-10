from sqlalchemy import text

from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo
from saalr_core.ids import new_id


async def _bootstrap_tenant(admin_engine, email: str, cuid: str):
    uid, tid, sid = new_id(), new_id(), new_id()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("SELECT auth_bootstrap(:uid, :tid, :sid, :cuid, :email)"),
            {"uid": str(uid), "tid": str(tid), "sid": str(sid), "cuid": cuid, "email": email},
        )
    return uid, tid


async def test_create_get_mark_save_roundtrip(app_sessionmaker, admin_engine):
    _uid, tid = await _bootstrap_tenant(admin_engine, "disc-repo@x.com", "ct_disc_repo")
    async with tenant_session(app_sessionmaker, tid) as s:
        did = await repo.create_discovery(s, tid, "AAPL", "US",
                                          request={"profile": "ev_to_risk", "top_n": 5})
    async with tenant_session(app_sessionmaker, tid) as s:
        await repo.mark_running(s, did)
    async with tenant_session(app_sessionmaker, tid) as s:
        await repo.save_result(s, did, {"results": []}, "succeeded", as_of="2026-06-10T20:00:00Z")
    async with tenant_session(app_sessionmaker, tid) as s:
        row = await repo.get_discovery(s, did)
        assert row.status == "succeeded"
        assert row.result_json == {"results": []}
        assert row.started_at is not None and row.completed_at is not None
