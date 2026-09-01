"""Conversation identity, replay, provenance, and evidence-time ordering."""

import json
import uuid
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from psycopg import connect, sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.campaigns.models import Campaign
from app.conversations.models import (
    Conversation,
    ConversationVersion,
    ConversationVersionObservation,
)
from app.conversations.service import current_version, normalize_observation
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.evidence.models import EvidenceBundle
from app.evidence.store import ArtifactInput, InMemoryEvidenceStore
from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.conftest import admin_database_url, configured_database_url
from tests.test_conversation_normalizer import thread_payload

CONVERSATION_DATABASE_NAME = "aptori_outreach_conversation_test"
CONVERSATION_DATABASE_URL = configured_database_url(CONVERSATION_DATABASE_NAME)


@pytest.fixture(scope="session")
def conversation_database_url() -> Iterator[str]:
    with connect(
        admin_database_url(CONVERSATION_DATABASE_URL), autocommit=True
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (CONVERSATION_DATABASE_NAME,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(CONVERSATION_DATABASE_NAME)
                )
            )
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", CONVERSATION_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield CONVERSATION_DATABASE_URL


def _payload(external_id: str, *, body: str = "Visible reply") -> list[Any]:
    payload = deepcopy(thread_payload(include_more=False))
    post = payload[0]["data"]["children"][0]["data"]
    comment = payload[1]["data"]["children"][0]["data"]
    post["id"] = external_id.removeprefix("t3_")
    post["name"] = external_id
    comment["parent_id"] = external_id
    comment["body"] = body
    return payload


def _seed_observation(
    session: Session,
    store: InMemoryEvidenceStore,
    tmp_path: Path,
    *,
    external_id: str,
    payload: list[Any],
    completed_at: datetime,
) -> RetrievalObservation:
    campaign = Campaign(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name=f"conversation-{uuid.uuid4().hex}",
        promotion_posture="expertise_first",
        status="active",
    )
    session.add(campaign)
    session.flush()
    run = DiscoveryRun(
        workspace_id=DEFAULT_WORKSPACE_ID,
        campaign_id=campaign.id,
        status="succeeded",
        method_plan={"queries": []},
        correlation_id=f"corr-{uuid.uuid4().hex[:20]}",
        completed_at=completed_at,
    )
    session.add(run)
    session.flush()
    raw_path = tmp_path / f"{uuid.uuid4().hex}.json"
    raw_path.write_text(json.dumps(payload))
    bundle = store.finalize_bundle(
        DEFAULT_WORKSPACE_ID,
        [
            ArtifactInput(
                "raw-thread-response.json",
                "raw",
                "application/json",
                raw_path,
            )
        ],
    )
    if session.get(EvidenceBundle, bundle.id) is None:
        session.add(
            EvidenceBundle(
                id=bundle.id,
                workspace_id=bundle.workspace_id,
                manifest_version=bundle.manifest_version,
                bundle_sha256=bundle.bundle_sha256,
                storage_key=bundle.storage_key,
                artifact_manifest=bundle.artifact_manifest,
            )
        )
        session.flush()
    descriptor = bundle.artifact_manifest["artifacts"]
    assert isinstance(descriptor, list)
    observation = RetrievalObservation(
        discovery_run_id=run.id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        query_id=f"thread_{uuid.uuid4().hex}",
        schema_version=1,
        capability="thread_fetch",
        provider_variant="test-thread",
        config_sha256="a" * 64,
        observation_id=f"observation-{uuid.uuid4().hex}",
        status="success",
        failure_class=None,
        failure_reason=None,
        source_url="https://www.reddit.com/r/example/comments/post/example/",
        final_url="https://www.reddit.com/r/example/comments/post/example/",
        external_source_id=external_id,
        candidate_count=0,
        candidates=[],
        normalized_sha256=None,
        normalized_content_sha256=None,
        elapsed_ms=1,
        started_at=completed_at,
        completed_at=completed_at,
        runtime={},
        network={},
        raw_artifact=descriptor[0],
        evidence_state="bundle",
        evidence_bundle_id=bundle.id,
        evidence_directory=None,
        correlation_id=run.correlation_id,
    )
    session.add(observation)
    session.flush()
    return observation


def test_replay_reuses_version_and_retains_every_observation_provenance(
    conversation_database_url: str, tmp_path: Path
) -> None:
    engine = create_engine(conversation_database_url)
    store = InMemoryEvidenceStore()
    external_id = f"t3_{uuid.uuid4().hex}"
    try:
        with Session(engine) as session, session.begin():
            first_observation = _seed_observation(
                session,
                store,
                tmp_path,
                external_id=external_id,
                payload=_payload(external_id),
                completed_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
            )
            second_observation = _seed_observation(
                session,
                store,
                tmp_path,
                external_id=external_id,
                payload=_payload(external_id),
                completed_at=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
            )
            first = normalize_observation(
                session, store, DEFAULT_WORKSPACE_ID, first_observation.id
            )
            second = normalize_observation(
                session, store, DEFAULT_WORKSPACE_ID, second_observation.id
            )
            replay = normalize_observation(
                session, store, DEFAULT_WORKSPACE_ID, first_observation.id
            )

            assert first.conversation.id == second.conversation.id
            assert first.version.id == second.version.id
            assert first.version_created is True
            assert second.version_created is False
            assert second.provenance_created is True
            assert replay.version_created is False
            assert replay.provenance_created is False
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Conversation)
                    .where(Conversation.id == first.conversation.id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ConversationVersion)
                    .where(ConversationVersion.conversation_id == first.conversation.id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ConversationVersionObservation)
                    .where(
                        ConversationVersionObservation.conversation_version_id
                        == first.version.id
                    )
                )
                == 2
            )

            v2 = normalize_observation(
                session,
                store,
                DEFAULT_WORKSPACE_ID,
                first_observation.id,
                normalizer_version="reddit-thread/v2",
            )
            assert v2.version.id != first.version.id
            assert (
                v2.version.normalized_content_sha256
                == first.version.normalized_content_sha256
            )
            assert v2.version.normalizer_version == "reddit-thread/v2"
    finally:
        engine.dispose()


def test_current_version_uses_evidence_time_not_normalization_order(
    conversation_database_url: str, tmp_path: Path
) -> None:
    engine = create_engine(conversation_database_url)
    store = InMemoryEvidenceStore()
    external_id = f"t3_{uuid.uuid4().hex}"
    try:
        with Session(engine) as session, session.begin():
            newer_evidence = _seed_observation(
                session,
                store,
                tmp_path,
                external_id=external_id,
                payload=_payload(external_id, body="newer evidence"),
                completed_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            )
            older_evidence = _seed_observation(
                session,
                store,
                tmp_path,
                external_id=external_id,
                payload=_payload(external_id, body="older evidence"),
                completed_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
            )
            older = normalize_observation(
                session, store, DEFAULT_WORKSPACE_ID, older_evidence.id
            )
            newer = normalize_observation(
                session, store, DEFAULT_WORKSPACE_ID, newer_evidence.id
            )
            selected = current_version(
                session, DEFAULT_WORKSPACE_ID, newer.conversation.id
            )

            assert older.version.id != newer.version.id
            assert selected is not None
            assert selected.id == newer.version.id
            with pytest.raises(LookupError):
                normalize_observation(session, store, uuid.uuid4(), newer_evidence.id)
    finally:
        engine.dispose()
