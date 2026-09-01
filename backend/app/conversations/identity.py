"""Stable job identity and wire-safe URL checks for run-scoped Candidates."""

import hashlib
from typing import TypeGuard

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

_HTTP_URL = TypeAdapter(AnyHttpUrl)


def thread_fetch_query_id(external_source_id: str) -> str:
    if not external_source_id:
        raise ValueError("external source id must be non-empty")
    digest = hashlib.sha256(external_source_id.encode()).hexdigest()[:32]
    return f"thread_{digest}"


def is_http_url(value: object) -> TypeGuard[str]:
    """True only for absolute http(s) URLs the REST contract can carry.

    The same predicate gates enqueueing and the transition read so that a
    Candidate is either fetchable and reportable, or neither.
    """
    if not isinstance(value, str) or not value:
        return False
    try:
        _HTTP_URL.validate_python(value)
    except ValidationError:
        return False
    return True
