"""SHA-256 hashing for receipt deduplication."""

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()
