"""Secret redaction (Phase 5 brief section 19). Provider adapters must
run any text that could contain the API key - an HTTP error body, a
caught exception's message - through `redact()` before it becomes part
of an `AIProviderError` message, a log line, or anything persisted to
`ai_actions`. Applied defensively even though a well-behaved API
shouldn't echo the key back: a key is sent only in a header, never a
URL or body, so under normal operation there is nothing to redact - this
exists for the abnormal case (a misconfigured proxy, a verbose error
page) where it might leak anyway.
"""

from __future__ import annotations


def redact(text: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text
