"""Database access for web-research sessions (migration 5). Mirrors
`app/ai/persistence.py`'s style - one module, no raw SQL anywhere else
in `app/research/`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database
from app.research.evidence import EvidenceItem
from app.research.session import WebResearchSessionRecord, WebResearchSessionStatus
from app.research.source import Source
from app.research.specification import StrategySpecification

_now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _session_row_to_record(row: Any) -> WebResearchSessionRecord:
    return WebResearchSessionRecord(
        id=row["id"],
        objective=row["objective"],
        status=WebResearchSessionStatus(row["status"]),
        iteration=row["iteration"],
        sources_discovered=row["sources_discovered"],
        sources_retrieved=row["sources_retrieved"],
        evidence_count=row["evidence_count"],
        specification_count=row["specification_count"],
        requests_made=row["requests_made"],
        stopping_reason=row["stopping_reason"],
        final_specification_status=row["final_specification_status"],
        provider_name=row["provider_name"],
        model_name=row["model_name"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def create_session(
    db: Database,
    *,
    session_id: str,
    objective: str,
    limits: Any,  # app.research.limits.WebResearchLimits
    provider_name: str,
    model_name: str,
) -> None:
    db.execute(
        """
        INSERT INTO web_research_sessions (
            id, objective, status, max_iterations, max_sources_per_session,
            max_requests_per_session, provider_name, model_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            objective,
            WebResearchSessionStatus.CREATED.value,
            limits.max_iterations,
            limits.max_sources_per_session,
            limits.max_requests_per_session,
            provider_name,
            model_name,
        ),
    )


def set_session_status(
    db: Database,
    session_id: str,
    status: WebResearchSessionStatus,
    *,
    started: bool = False,
    completed: bool = False,
    stopping_reason: str | None = None,
    final_specification_status: str | None = None,
) -> None:
    fields = ["status = ?"]
    params: list[Any] = [status.value]
    if started:
        fields.append("started_at = ?")
        params.append(_now())
    if completed:
        fields.append("completed_at = ?")
        params.append(_now())
    if stopping_reason is not None:
        fields.append("stopping_reason = ?")
        params.append(stopping_reason)
    if final_specification_status is not None:
        fields.append("final_specification_status = ?")
        params.append(final_specification_status)
    params.append(session_id)
    db.execute(f"UPDATE web_research_sessions SET {', '.join(fields)} WHERE id = ?", params)


def update_session_progress(
    db: Database,
    session_id: str,
    *,
    iteration: int,
    sources_discovered: int,
    sources_retrieved: int,
    evidence_count: int,
    specification_count: int,
    requests_made: int,
) -> None:
    db.execute(
        """
        UPDATE web_research_sessions SET
            iteration = ?, sources_discovered = ?, sources_retrieved = ?,
            evidence_count = ?, specification_count = ?, requests_made = ?
        WHERE id = ?
        """,
        (iteration, sources_discovered, sources_retrieved, evidence_count, specification_count, requests_made, session_id),
    )


def load_session(db: Database, session_id: str) -> WebResearchSessionRecord | None:
    row = db.query_one("SELECT * FROM web_research_sessions WHERE id = ?", (session_id,))
    return _session_row_to_record(row) if row else None


def save_source(db: Database, session_id: str, source: Source) -> None:
    """Upsert by id: `WebResearchAgent` reuses one `Source.id` across a
    URL's whole lifecycle (discovered -> retrieved/cached/failed, brief
    section 20's deduplication) and calls this again each time that
    status changes - it must update the existing row, not fail on a
    duplicate primary key."""
    db.execute(
        """
        INSERT INTO web_sources (
            id, session_id, url, normalized_url, source_type, status, title, domain,
            publisher, author, published_at, last_modified_at, retrieved_at,
            content_hash, content_type, byte_size, http_status, trust_metadata,
            discovery_query, failure_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            status = excluded.status,
            title = excluded.title,
            domain = excluded.domain,
            publisher = excluded.publisher,
            author = excluded.author,
            published_at = excluded.published_at,
            last_modified_at = excluded.last_modified_at,
            retrieved_at = excluded.retrieved_at,
            content_hash = excluded.content_hash,
            content_type = excluded.content_type,
            byte_size = excluded.byte_size,
            http_status = excluded.http_status,
            trust_metadata = excluded.trust_metadata,
            discovery_query = excluded.discovery_query,
            failure_reason = excluded.failure_reason
        """,
        (
            source.id,
            session_id,
            source.url,
            source.normalized_url,
            source.source_type.value,
            source.status.value,
            source.title,
            source.domain,
            source.publisher,
            source.author,
            source.published_at,
            source.last_modified_at,
            source.retrieved_at,
            source.content_hash,
            source.content_type,
            source.byte_size,
            source.http_status,
            json.dumps(
                {
                    "https": source.trust.https,
                    "domain": source.trust.domain,
                    "has_author": source.trust.has_author,
                    "has_published_date": source.trust.has_published_date,
                    "retrieval_succeeded": source.trust.retrieval_succeeded,
                    "content_is_complete": source.trust.content_is_complete,
                }
            ),
            source.discovery_query,
            source.failure_reason,
        ),
    )


def list_sources(db: Database, session_id: str) -> list[dict[str, Any]]:
    rows = db.query_all("SELECT * FROM web_sources WHERE session_id = ? ORDER BY created_at", (session_id,))
    return [dict(row) for row in rows]


def save_evidence(db: Database, session_id: str, evidence: EvidenceItem) -> None:
    db.execute(
        """
        INSERT INTO web_evidence (
            id, session_id, source_id, claim, status, location_reference,
            quoted_text, extraction_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.id,
            session_id,
            evidence.source_id,
            evidence.claim,
            evidence.status.value,
            evidence.location_reference,
            evidence.quoted_text,
            evidence.extraction_timestamp,
        ),
    )


def list_evidence(db: Database, session_id: str, *, source_id: str | None = None) -> list[dict[str, Any]]:
    if source_id is not None:
        rows = db.query_all(
            "SELECT * FROM web_evidence WHERE session_id = ? AND source_id = ? ORDER BY created_at",
            (session_id, source_id),
        )
    else:
        rows = db.query_all("SELECT * FROM web_evidence WHERE session_id = ? ORDER BY created_at", (session_id,))
    return [dict(row) for row in rows]


def _serialize_specification(spec: StrategySpecification) -> dict[str, Any]:
    import dataclasses
    from enum import Enum

    def default(obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        return str(obj)

    return json.loads(json.dumps(dataclasses.asdict(spec), default=default))


def save_specification(db: Database, session_id: str, spec: StrategySpecification, *, validation_errors: tuple[str, ...] = ()) -> str:
    """Always inserts a new row (one row per revision) - `web_strategy_
    specifications` is an append-only audit trail of how a specification
    evolved across iterations, not a single mutable record."""
    row_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO web_strategy_specifications (
            id, session_id, name, status, specification, validation_errors,
            unknowns, ambiguities, source_evidence_ids
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            session_id,
            spec.name,
            spec.status.value,
            json.dumps(_serialize_specification(spec)),
            json.dumps(list(validation_errors)),
            json.dumps(list(spec.unknowns)),
            json.dumps(list(spec.ambiguities)),
            json.dumps(list(spec.source_evidence_ids)),
        ),
    )
    return row_id


def list_specifications(db: Database, session_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM web_strategy_specifications WHERE session_id = ? ORDER BY created_at", (session_id,)
    )
    return [dict(row) for row in rows]


def record_decision(
    db: Database,
    *,
    session_id: str,
    iteration: int,
    action: str,
    reasoning_summary: str,
    details: dict[str, Any],
    stopping_reason: str | None,
) -> None:
    db.execute(
        """
        INSERT INTO web_research_decisions (id, session_id, iteration, action, reasoning_summary, details, stopping_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), session_id, iteration, action, reasoning_summary, json.dumps(details, default=str), stopping_reason),
    )


def list_decisions(db: Database, session_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM web_research_decisions WHERE session_id = ? ORDER BY iteration", (session_id,)
    )
    return [dict(row) for row in rows]
