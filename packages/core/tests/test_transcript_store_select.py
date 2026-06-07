from saalr_core.research.transcript_store import (
    DbTranscriptStore,
    S3TranscriptStore,
    make_transcript_store,
)


class _Settings:
    def __init__(self, bucket=None, region=None, endpoint_url=None):
        self.transcript_s3_bucket = bucket
        self.aws_region = region
        self.aws_endpoint_url = endpoint_url


def test_make_transcript_store_picks_s3_when_bucket_set():
    store = make_transcript_store(_Settings(bucket="b", region="us-east-1"), object())
    assert isinstance(store, S3TranscriptStore)


def test_make_transcript_store_defaults_to_db():
    store = make_transcript_store(_Settings(bucket=None), object())
    assert isinstance(store, DbTranscriptStore)
