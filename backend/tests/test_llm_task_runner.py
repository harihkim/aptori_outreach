"""LLM Task Runner: configuration routing, Model Run provenance, failure classes."""

import asyncio
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, Field
from pydantic_ai import models as pydantic_ai_models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.config import Settings
from app.llm.models import MODEL_RUN_FAILURE_CLASSES
from app.llm.runner import (
    DomainValidationError,
    LLMTaskRunner,
    TaskSpec,
    resolve_endpoint,
    sha256_of,
)
from app.workspaces import DEFAULT_WORKSPACE_ID

INPUT_SHA = "1" * 64


class Verdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    label: str


SPEC: TaskSpec[Verdict] = TaskSpec(
    task_id="probe_task",
    task_version="1",
    prompt_version="2026-09-02.1",
    schema_version="1",
    eval_suite_id="probe/frozen",
    instructions="Return a verdict.",
    output_type=Verdict,
)


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def function_model(args_per_call: list[dict[str, Any]]) -> FunctionModel:
    calls: list[dict[str, Any]] = list(args_per_call)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        args = calls.pop(0) if calls else args_per_call[-1]
        tool = info.output_tools[0]
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=args)],
            model_name="fn-under-test",
        )

    return FunctionModel(respond, model_name="fn-under-test")


def run(runner: LLMTaskRunner, **kwargs: Any) -> Any:
    return asyncio.run(
        runner.run(
            SPEC,
            workspace_id=DEFAULT_WORKSPACE_ID,
            correlation_id="corr-llm",
            user_prompt="Judge this.",
            input_sha256=INPUT_SHA,
            **kwargs,
        )
    )


def test_suite_blocks_real_model_requests_by_default() -> None:
    assert pydantic_ai_models.ALLOW_MODEL_REQUESTS is False


def test_successful_run_records_versions_routing_usage_and_output_digest() -> None:
    runner = LLMTaskRunner(settings=settings(), model_override=TestModel())

    result = run(runner)

    assert result.succeeded
    assert isinstance(result.output, Verdict)
    row = result.model_run
    assert row.status == "succeeded"
    assert row.failure_class is None
    assert (row.task_id, row.task_version, row.prompt_version, row.schema_version) == (
        "probe_task",
        "1",
        "2026-09-02.1",
        "1",
    )
    assert row.eval_suite_id == "probe/frozen"
    assert row.model_tier == "ordinary"
    assert row.served_tier == "ordinary"
    assert row.requested_model == "test"
    assert row.actual_model == "test"
    assert row.endpoint_label == "override"
    assert row.request_count == 1
    assert row.output_retry_count == 0
    assert row.input_tokens is not None and row.output_tokens is not None
    assert row.input_sha256 == INPUT_SHA
    assert row.output_sha256 == sha256_of(result.output.model_dump(mode="json"))
    assert row.cost_status == "unpriced"
    assert row.retention_policy == "hashes_only"
    assert row.correlation_id == "corr-llm"
    assert row.workspace_id == DEFAULT_WORKSPACE_ID
    assert row.completed_at >= row.started_at
    assert row.model_settings == {
        "request_limit": 3,
        "output_retries": 1,
        "total_tokens_limit": 24_000,
        "timeout_seconds": 60,
    }


def test_invalid_output_exhausts_model_retries_and_yields_no_output() -> None:
    model = function_model([{"score": 7.0, "label": "too high"}])
    runner = LLMTaskRunner(settings=settings(), model_override=model)

    result = run(runner)

    assert result.output is None
    row = result.model_run
    assert row.status == "failed"
    assert row.failure_class == "output_invalid"
    assert row.output_sha256 is None
    assert "too high" not in (row.failure_reason or "")


def test_model_retry_budget_is_counted_when_the_second_attempt_succeeds() -> None:
    model = function_model(
        [{"score": 7.0, "label": "bad"}, {"score": 0.4, "label": "fixed"}]
    )
    runner = LLMTaskRunner(settings=settings(), model_override=model)

    result = run(runner)

    assert result.succeeded
    assert result.output is not None and result.output.label == "fixed"
    assert result.model_run.request_count == 2
    assert result.model_run.output_retry_count == 1
    assert result.model_run.actual_model == "fn-under-test"


def test_domain_validation_failure_is_recorded_with_usage_but_no_output() -> None:
    model = function_model([{"score": 0.9, "label": "inconsistent"}])
    runner = LLMTaskRunner(settings=settings(), model_override=model)

    def reject(verdict: Verdict) -> None:
        raise DomainValidationError(f"label {verdict.label!r} is not allowed")

    result = run(runner, domain_validator=reject)

    assert result.output is None
    row = result.model_run
    assert row.status == "failed"
    assert row.failure_class == "domain_validation_failed"
    assert row.request_count == 1
    assert row.actual_model == "fn-under-test"


def test_unconfigured_endpoint_fails_closed_without_a_request() -> None:
    runner = LLMTaskRunner(settings=settings())

    result = run(runner)

    assert result.output is None
    row = result.model_run
    assert row.failure_class == "model_unconfigured"
    assert row.request_count == 0
    assert row.requested_model is None
    assert row.endpoint_label is None
    assert "APTORI_LLM_BASE_URL" in (row.failure_reason or "")


def test_configured_endpoint_is_blocked_by_the_suite_guard_not_by_code() -> None:
    configured = settings(
        llm_base_url="http://127.0.0.1:9/v1", llm_model="probe-model", llm_api_key="k"
    )
    runner = LLMTaskRunner(settings=configured)

    result = run(runner)

    assert result.output is None
    row = result.model_run
    assert row.failure_class == "model_requests_blocked"
    assert row.requested_model == "probe-model"
    assert row.endpoint_label == "127.0.0.1"
    assert "k" not in (row.failure_reason or "").split()


def test_every_failure_class_is_in_the_persisted_vocabulary() -> None:
    assert set(MODEL_RUN_FAILURE_CLASSES) == {
        "model_unconfigured",
        "model_requests_blocked",
        "model_request_failed",
        "output_invalid",
        "usage_limit_exceeded",
        "domain_validation_failed",
    }


def test_strong_tier_falls_back_to_ordinary_until_configured() -> None:
    ordinary_only = settings(
        llm_base_url="https://llm.example.test/v1",
        llm_model="ordinary-m",
        llm_api_key="a",
    )
    endpoint = resolve_endpoint(ordinary_only, "strong")
    assert endpoint is not None
    assert (endpoint.requested_tier, endpoint.served_tier) == ("strong", "ordinary")
    assert endpoint.model_name == "ordinary-m"
    assert endpoint.label == "llm.example.test"

    both = settings(
        llm_base_url="https://llm.example.test/v1",
        llm_model="ordinary-m",
        llm_api_key="a",
        llm_strong_base_url="https://strong.example.test/v1",
        llm_strong_model="strong-m",
        llm_strong_api_key="b",
    )
    strong = resolve_endpoint(both, "strong")
    assert strong is not None
    assert (strong.served_tier, strong.model_name) == ("strong", "strong-m")
    assert resolve_endpoint(settings(), "ordinary") is None
    with pytest.raises(ValueError, match="unknown model tier"):
        resolve_endpoint(both, "premium")


def test_blank_llm_configuration_reads_as_unset() -> None:
    blank = settings(llm_base_url="  ", llm_model="", llm_api_key=" ")
    assert (blank.llm_base_url, blank.llm_model, blank.llm_api_key) == (
        None,
        None,
        None,
    )


def test_input_digest_is_canonical_and_stable() -> None:
    first = sha256_of({"b": 1, "a": [uuid.UUID(int=1)]})
    second = sha256_of({"a": [uuid.UUID(int=1)], "b": 1})
    assert first == second
    assert first != sha256_of({"a": [uuid.UUID(int=2)], "b": 1})
