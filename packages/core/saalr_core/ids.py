from uuid import UUID

from uuid_utils.compat import uuid7


def new_id() -> UUID:
    """Return a time-ordered UUIDv7 as a stdlib uuid.UUID."""
    return uuid7()