"""Execute one versioned LLM Task and record it as a Model Run.

The runner is deliberately small: it resolves an endpoint from settings,
runs a Pydantic AI ``Agent`` for a typed output, applies the caller's domain
validators, and returns both the outcome and an unsaved ``ModelRun`` row.
The caller decides the transaction; the runner never commits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel
from pydantic_ai import Agent, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from app.config import Settings, get_settings
from app.llm.models import (
    COST_UNPRICED,
    MODEL_TIERS,
    RETENTION_HASHES_ONLY,
    ModelRun,
)

logger = logging.getLogger(__name__)


class DomainValidationError(ValueError):
    """A schema-valid output violates a business rule; nothing is scored."""


@dataclass(frozen=True, slots=True)
class TaskSpec[OutputT: BaseModel]:
    """Everything that identifies one LLM Task independent of any input."""

    task_id: str
    task_version: str
    prompt_version: str
    schema_version: str
    eval_suite_id: str
    instructions: str
    output_type: type[OutputT]


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    """One resolved tier: which model, where, and how it is labelled."""

    requested_tier: str
    served_tier: str
    base_url: str
    model_name: str
    api_key: str

    @property
    def label(self) -> str:
        host = urlsplit(self.base_url).hostname
        return host or "configured-endpoint"


@dataclass(frozen=True, slots=True)
class TaskRunResult[OutputT: BaseModel]:
    """The settled attempt: the Model Run row plus the validated output."""

    model_run: ModelRun
    output: OutputT | None

    @property
    def succeeded(self) -> bool:
        return self.output is not None


def resolve_endpoint(settings: Settings, tier: str) -> ModelEndpoint | None:
    """Resolve a tier from configuration; strong falls back to ordinary.

    Returns ``None`` when the ordinary tier is unconfigured: the runner then
    records ``model_unconfigured`` and never opens a connection.
    """
    if tier not in MODEL_TIERS:
        raise ValueError(f"unknown model tier: {tier!r}")
    if (
        tier == "strong"
        and settings.llm_strong_base_url
        and settings.llm_strong_model
        and settings.llm_strong_api_key
    ):
        return ModelEndpoint(
            requested_tier=tier,
            served_tier="strong",
            base_url=settings.llm_strong_base_url,
            model_name=settings.llm_strong_model,
            api_key=settings.llm_strong_api_key,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        return ModelEndpoint(
            requested_tier=tier,
            served_tier="ordinary",
            base_url=settings.llm_base_url,
            model_name=settings.llm_model,
            api_key=settings.llm_api_key,
        )
    return None


def build_model(endpoint: ModelEndpoint) -> Model:
    """Instantiate the OpenAI-compatible chat model for one endpoint."""
    return OpenAIChatModel(
        endpoint.model_name,
        provider=OpenAIProvider(base_url=endpoint.base_url, api_key=endpoint.api_key),
    )


def sha256_of(value: Any) -> str:
    """Digest of the canonical JSON form; the only trace prompts leave."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _redact(error: BaseException) -> str:
    """Name the failure without echoing prompts, completions, or secrets."""
    return f"{type(error).__name__}: {str(error)[:200]}"


class LLMTaskRunner:
    """Run typed LLM Tasks under configuration-owned routing and limits.

    ``model_override`` is the test seam (``TestModel``/``FunctionModel``); a
    production runner leaves it unset and resolves the tier from settings.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model_override: Model | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._model_override = model_override

    async def run[OutputT: BaseModel](
        self,
        spec: TaskSpec[OutputT],
        *,
        workspace_id: uuid.UUID,
        correlation_id: str,
        user_prompt: str,
        input_sha256: str,
        tier: str = "ordinary",
        domain_validator: Callable[[OutputT], None] | None = None,
    ) -> TaskRunResult[OutputT]:
        started_at = datetime.now(UTC)
        endpoint = resolve_endpoint(self._settings, tier)
        model: Model | None = self._model_override
        if model is None and endpoint is not None:
            model = build_model(endpoint)

        def settle(
            *,
            status: str,
            output: OutputT | None = None,
            failure_class: str | None = None,
            failure_reason: str | None = None,
            usage: Any = None,
            actual_model: str | None = None,
            run_reference: str | None = None,
        ) -> TaskRunResult[OutputT]:
            requests = int(getattr(usage, "requests", 0) or 0)
            row = ModelRun(
                workspace_id=workspace_id,
                task_id=spec.task_id,
                task_version=spec.task_version,
                prompt_version=spec.prompt_version,
                schema_version=spec.schema_version,
                eval_suite_id=spec.eval_suite_id,
                model_tier=tier,
                served_tier=endpoint.served_tier if endpoint else tier,
                requested_model=(
                    endpoint.model_name
                    if endpoint
                    else getattr(model, "model_name", None)
                ),
                actual_model=actual_model,
                endpoint_label=(
                    endpoint.label
                    if endpoint
                    else ("override" if self._model_override else None)
                ),
                model_settings={
                    "request_limit": self._settings.llm_request_limit,
                    "output_retries": self._settings.llm_output_retries,
                    "total_tokens_limit": self._settings.llm_total_tokens_limit,
                    "timeout_seconds": self._settings.llm_timeout_seconds,
                },
                input_sha256=input_sha256,
                output_sha256=(
                    sha256_of(output.model_dump(mode="json"))
                    if output is not None
                    else None
                ),
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                request_count=requests,
                # Every request past the first was a model-facing retry of
                # a rejected output; transport retries live below this layer.
                output_retry_count=max(requests - 1, 0),
                cost_status=COST_UNPRICED,
                retention_policy=RETENTION_HASHES_ONLY,
                status=status,
                failure_class=failure_class,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
                run_reference=run_reference,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            return TaskRunResult(model_run=row, output=output)

        if model is None:
            return settle(
                status="failed",
                failure_class="model_unconfigured",
                failure_reason=(
                    "no ordinary-tier LLM endpoint is configured "
                    "(APTORI_LLM_BASE_URL, APTORI_LLM_MODEL, APTORI_LLM_API_KEY)"
                ),
            )

        agent: Agent[None, OutputT] = Agent(
            model,
            output_type=spec.output_type,
            instructions=spec.instructions,
            name=spec.task_id,
            retries=self._settings.llm_output_retries,
        )
        limits = UsageLimits(
            request_limit=self._settings.llm_request_limit,
            total_tokens_limit=self._settings.llm_total_tokens_limit,
        )
        try:
            result = await agent.run(
                user_prompt,
                usage_limits=limits,
                model_settings={"timeout": self._settings.llm_timeout_seconds},
            )
        except UsageLimitExceeded as error:
            return settle(
                status="failed",
                failure_class="usage_limit_exceeded",
                failure_reason=_redact(error),
            )
        except UnexpectedModelBehavior as error:
            return settle(
                status="failed",
                failure_class="output_invalid",
                failure_reason=_redact(error),
            )
        except RuntimeError as error:
            if "ALLOW_MODEL_REQUESTS" in str(error):
                return settle(
                    status="failed",
                    failure_class="model_requests_blocked",
                    failure_reason=_redact(error),
                )
            logger.warning("LLM task request failed", exc_info=True)
            return settle(
                status="failed",
                failure_class="model_request_failed",
                failure_reason=_redact(error),
            )
        except Exception as error:  # noqa: BLE001 - classified, never raised
            logger.warning("LLM task request failed", exc_info=True)
            return settle(
                status="failed",
                failure_class="model_request_failed",
                failure_reason=_redact(error),
            )

        output = result.output
        usage = result.usage
        actual_model = getattr(result.response, "model_name", None)
        run_reference = getattr(result, "run_id", None)
        if domain_validator is not None:
            try:
                domain_validator(output)
            except DomainValidationError as error:
                return settle(
                    status="failed",
                    failure_class="domain_validation_failed",
                    failure_reason=_redact(error),
                    usage=usage,
                    actual_model=actual_model,
                    run_reference=run_reference,
                )
        return settle(
            status="succeeded",
            output=output,
            usage=usage,
            actual_model=actual_model,
            run_reference=run_reference,
        )
