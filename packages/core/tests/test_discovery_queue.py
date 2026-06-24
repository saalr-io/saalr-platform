import uuid
from saalr_core.queue.discovery_queue import Job, STREAM, GROUP, _parse


def test_constants():
    assert STREAM == "saalr:disc:jobs:v1"
    assert GROUP == "disc-workers"


def test_parse_builds_jobs():
    tid, did = uuid.uuid4(), uuid.uuid4()
    jobs = _parse([("1-0", {"tenant_id": str(tid), "discovery_id": str(did)})])
    assert jobs == [Job(msg_id="1-0", tenant_id=tid, discovery_id=did)]


def test_parse_skips_empty_fields():
    assert _parse([("1-0", {})]) == []
