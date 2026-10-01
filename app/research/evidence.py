"""Structured, source-traceable evidence (Phase 6 brief section 13).

`extract_evidence()` is a deterministic, keyword/sentence-based matcher -
no AI, no network, fully testable in isolation. It is intentionally
simple: for each topic of interest (e.g. "entry", "stop loss"), it finds
sentences in the normalized source text that mention it and records them
as `EXPLICIT` evidence, quoting the exact sentence. A topic with no
matching sentence becomes an `UNKNOWN` evidence item rather than being
silently omitted - the absence of information is itself a recorded fact
(brief section 15: "the system must NOT invent details").

`INFERRED` is reserved for an AI's own interpretation of ambiguous or
incomplete evidence (set by whatever constructs the strategy
specification from these items, never by this module) - this file only
ever produces `EXPLICIT` (quoted, found) or `UNKNOWN` (topic, not found)
items, because it has no interpretive capability of its own.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

DEFAULT_TOPICS: tuple[str, ...] = (
    "entry",
    "exit",
    "stop loss",
    "take profit",
    "timeframe",
    "indicator",
    "confirmation",
    "session",
    "filter",
)


class EvidenceStatus(str, Enum):
    EXPLICIT = "explicit"  # a direct quote from a source
    INFERRED = "inferred"  # an AI's interpretation, not a direct quote
    UNKNOWN = "unknown"  # looked for, not found


def new_evidence_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    claim: str  # what topic/question this evidence addresses
    status: EvidenceStatus
    location_reference: str | None = None  # e.g. "sentence 12"
    quoted_text: str | None = None  # verbatim text from the source; None for UNKNOWN
    extraction_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=new_evidence_id)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def extract_evidence(
    source_id: str, normalized_text: str, *, topics: tuple[str, ...] = DEFAULT_TOPICS
) -> list[EvidenceItem]:
    sentences = _split_sentences(normalized_text)
    items: list[EvidenceItem] = []
    for topic in topics:
        pattern = re.compile(re.escape(topic), re.IGNORECASE)
        matched = False
        for index, sentence in enumerate(sentences):
            if pattern.search(sentence):
                items.append(
                    EvidenceItem(
                        source_id=source_id,
                        claim=topic,
                        status=EvidenceStatus.EXPLICIT,
                        location_reference=f"sentence {index}",
                        quoted_text=sentence,
                    )
                )
                matched = True
        if not matched:
            items.append(
                EvidenceItem(
                    source_id=source_id,
                    claim=topic,
                    status=EvidenceStatus.UNKNOWN,
                    location_reference=None,
                    quoted_text=None,
                )
            )
    return items
