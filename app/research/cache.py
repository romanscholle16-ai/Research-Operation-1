"""Bounded, project-local source cache (Phase 6 brief sections 20-21).

Lives under `data/cache/web_sources/` (Phase 1's existing `data/cache/`
tree - no new top-level directory). Keyed by normalized URL
(`source.py::normalize_url`), so trivial formatting differences in a URL
hit the same cache entry rather than being treated as a different source
(brief section 20).

Bounded by both entry count and total bytes (`WebResearchLimits.
max_cache_entries`/`max_cache_bytes`, human-controlled, not AI-settable -
there is no code path here that takes a limit from AI output). Eviction
is oldest-by-retrieval-time first, applied after every write. Never
caches a URL whose retrieval wasn't a plain, successful, unauthenticated
GET - there is nothing resembling a credential or auth header anywhere
in what gets written, because `HttpSourceRetriever` never sends one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedSource:
    normalized_url: str
    content: bytes
    content_type: str | None
    content_hash: str
    retrieved_at: str


def _key(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


class SourceCache:
    def __init__(self, cache_dir: Path, *, max_entries: int, max_bytes: int) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_entries = max_entries
        self._max_bytes = max_bytes

    def get(self, normalized_url: str) -> CachedSource | None:
        meta_path = self._dir / f"{_key(normalized_url)}.json"
        content_path = self._dir / f"{_key(normalized_url)}.bin"
        if not meta_path.exists() or not content_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        content = content_path.read_bytes()
        return CachedSource(
            normalized_url=normalized_url,
            content=content,
            content_type=meta.get("content_type"),
            content_hash=meta.get("content_hash", ""),
            retrieved_at=meta.get("retrieved_at", ""),
        )

    def put(self, normalized_url: str, content: bytes, *, content_type: str | None, content_hash: str, retrieved_at: str) -> None:
        key = _key(normalized_url)
        (self._dir / f"{key}.bin").write_bytes(content)
        (self._dir / f"{key}.json").write_text(
            json.dumps(
                {
                    "url": normalized_url,
                    "content_type": content_type,
                    "content_hash": content_hash,
                    "retrieved_at": retrieved_at,
                }
            ),
            encoding="utf-8",
        )
        self._enforce_bounds()

    def _entries(self) -> list[Path]:
        return sorted(self._dir.glob("*.bin"), key=lambda p: p.stat().st_mtime)

    def _enforce_bounds(self) -> None:
        entries = self._entries()
        total_bytes = sum(p.stat().st_size for p in entries)
        # Oldest-first eviction until both bounds are satisfied.
        while entries and (len(entries) > self._max_entries or total_bytes > self._max_bytes):
            oldest = entries.pop(0)
            total_bytes -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            (oldest.with_suffix(".json")).unlink(missing_ok=True)

    def stats(self) -> tuple[int, int]:
        entries = self._entries()
        return len(entries), sum(p.stat().st_size for p in entries)
