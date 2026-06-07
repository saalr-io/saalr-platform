import os
from uuid import uuid4

import pytest

boto3 = pytest.importorskip("boto3")

from saalr_core.research.transcript_store import S3TranscriptStore  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("AWS_ENDPOINT_URL"), reason="LocalStack/AWS endpoint not configured")

_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL")
_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
_BUCKET = "saalr-transcripts-test"


def _ensure_bucket():
    c = boto3.client("s3", region_name=_REGION, endpoint_url=_ENDPOINT)
    try:
        c.create_bucket(Bucket=_BUCKET)
    except Exception:  # noqa: BLE001 - already exists is fine
        pass


async def test_s3_save_load_roundtrip():
    _ensure_bucket()
    store = S3TranscriptStore(_BUCKET, region=_REGION, endpoint_url=_ENDPOINT)
    tid, nid = uuid4(), uuid4()
    steps = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]
    await store.save(tenant_id=tid, note_id=nid, steps=steps)
    assert await store.load(tenant_id=tid, note_id=nid) == steps
    assert await store.load(tenant_id=tid, note_id=uuid4()) is None
