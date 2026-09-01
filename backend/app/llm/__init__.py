"""LLM Task Runner boundary: typed, versioned, configuration-routed model calls.

Application code owns state transitions, whole-job retries, idempotency,
scoring, persistence, and authorization (ADR-005). This package owns one
thing: executing a named LLM Task through Pydantic AI against an endpoint
resolved purely from configuration (ADR-014) and recording every attempt as
an immutable Model Run.
"""

from app.llm.models import ModelRun

__all__ = ["ModelRun"]
