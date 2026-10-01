"""The structured representation of one research source (Phase 6 brief
section 7). A `Source` never invents metadata - every field is either
what was actually observed on retrieval (URL, domain, content hash,
HTTP status) or explicitly `None`/empty when unknown. The URL plus
`content_hash` are what make a piece of research reproducible/auditable:
given the same URL and the same hash, anyone can confirm this is the
exact content the research session actually saw.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit, urlunsplit


class SourceType(str, Enum):
    WEB_PAGE = "web_page"
    DOCUMENTATION = "documentation"
    ARTICLE = "article"
    RESEARCH_PAPER = "research_paper"
    PDF = "pdf"
    TEXT_RESOURCE = "text_resource"
    UNKNOWN = "unknown"


class SourceStatus(str, Enum):
    DISCOVERED = "discovered"  # known about, not yet retrieved
    RETRIEVED = "retrieved"
    CACHED = "cached"  # served from the local cache, not re-fetched
    ACCESS_DENIED = "access_denied"  # robots.txt, auth wall, paywall, CAPTCHA, etc.
    FAILED = "failed"  # timeout, network error, oversized, unreadable


def extract_domain(url: str) -> str:
    return urlsplit(url).netloc.lower()


def normalize_url(url: str) -> str:
    """A conservative normalization for deduplication (brief section 20):
    lowercases scheme/host, drops a trailing slash and URL fragment.
    Does NOT reorder or drop query parameters - two URLs that differ only
    by query string may genuinely be different documents."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def new_source_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class TrustSignals:
    """Deterministic, observable facts about a source - never a single
    AI-invented "trust score" (brief section 12). Each field is either
    objectively true/false/known, or `None` when genuinely unknown -
    uncertainty is preserved, not resolved by guessing."""

    https: bool = False
    domain: str = ""
    has_author: bool = False
    has_published_date: bool = False
    retrieval_succeeded: bool = False
    content_is_complete: bool | None = None  # None = unknown (e.g. truncated at max_response_bytes)


@dataclass(frozen=True)
class Source:
    url: str
    source_type: SourceType = SourceType.UNKNOWN
    status: SourceStatus = SourceStatus.DISCOVERED
    title: str | None = None
    domain: str = ""
    publisher: str | None = None
    author: str | None = None
    published_at: str | None = None  # ISO string if known; never invented
    last_modified_at: str | None = None
    retrieved_at: str | None = None
    content_hash: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    http_status: int | None = None
    trust: TrustSignals = field(default_factory=TrustSignals)
    discovery_query: str | None = None
    failure_reason: str | None = None
    id: str = field(default_factory=new_source_id)

    @property
    def normalized_url(self) -> str:
        return normalize_url(self.url)
