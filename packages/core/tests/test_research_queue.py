from uuid import uuid4

from saalr_core.queue.research_queue import GROUP, STREAM, Job, _parse


def test_constants_are_research_scoped():
    assert STREAM == "saalr:research:jobs:v1"
    assert GROUP == "research-workers"


def test_parse_builds_jobs_and_skips_deleted_entries():
    tid, nid = uuid4(), uuid4()
    entries = [
        ("1-0", {"tenant_id": str(tid), "note_id": str(nid)}),
        ("2-0", None),  # an entry deleted between pending and claim
    ]
    jobs = _parse(entries)
    assert jobs == [Job(msg_id="1-0", tenant_id=tid, note_id=nid)]
