"""Stable job identity for one run-scoped thread-fetch candidate."""

import hashlib


def thread_fetch_query_id(external_source_id: str) -> str:
    if not external_source_id:
        raise ValueError("external source id must be non-empty")
    digest = hashlib.sha256(external_source_id.encode()).hexdigest()[:32]
    return f"thread_{digest}"
