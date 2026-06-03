from __future__ import annotations

import asyncio
import json
from typing import Protocol, runtime_checkable

from saalr_core.db.session import tenant_session
from saalr_core.research import transcript_repo


@runtime_checkable
class TranscriptStore(Protocol):
    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None: ...
    async def load(self, *, tenant_id, note_id) -> list[dict] | None: ...


class DbTranscriptStore:
    """Postgres-backed transcript store. Each method opens its own tenant session, so the
    TranscriptStore interface stays backend-agnostic (an S3TranscriptStore swaps in later)."""

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None:
        async with tenant_session(self._sm, tenant_id) as s:
            await transcript_repo.insert_transcript(s, tenant_id=tenant_id, note_id=note_id, steps=steps)

    async def load(self, *, tenant_id, note_id) -> list[dict] | None:
        async with tenant_session(self._sm, tenant_id) as s:
            return await transcript_repo.get_transcript(s, note_id)


class S3TranscriptStore:
    """S3-backed transcript store. Sync boto3 is off-loaded via asyncio.to_thread so the async
    TranscriptStore interface holds no thread/loop. boto3 is imported lazily (optional `aws` extra)."""

    def __init__(self, bucket, *, client=None, region=None, endpoint_url=None, prefix="transcripts"):
        self._bucket = bucket
        self._client = client            # injectable for tests; else lazy-built
        self._region = region
        self._endpoint = endpoint_url
        self._prefix = prefix

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self._region, endpoint_url=self._endpoint)
        return self._client

    def _key(self, tenant_id, note_id) -> str:
        return f"{self._prefix}/{tenant_id}/{note_id}.json"

    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None:
        client = self._get_client()
        body = json.dumps(steps).encode("utf-8")
        await asyncio.to_thread(
            client.put_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id),
            Body=body, ContentType="application/json")

    async def load(self, *, tenant_id, note_id) -> list[dict] | None:
        client = self._get_client()
        try:
            resp = await asyncio.to_thread(
                client.get_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id))
        except client.exceptions.NoSuchKey:
            return None
        body = await asyncio.to_thread(resp["Body"].read)
        return json.loads(body)


def make_transcript_store(settings, sessionmaker) -> TranscriptStore:
    """S3 store when `transcript_s3_bucket` is configured, else the Postgres store."""
    bucket = getattr(settings, "transcript_s3_bucket", None)
    if bucket:
        return S3TranscriptStore(
            bucket, region=getattr(settings, "aws_region", None),
            endpoint_url=getattr(settings, "aws_endpoint_url", None))
    return DbTranscriptStore(sessionmaker)
