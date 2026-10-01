"""Source content normalization (Phase 6 brief section 6/9: "normalize
encoding"). Stdlib-only HTML-to-text extraction via `html.parser` - no
BeautifulSoup/lxml dependency. Deliberately simple: strips tags and
scripts/styles, collapses whitespace, keeps the actual readable text.
Good enough for keyword-based evidence extraction (evidence.py); not a
general-purpose HTML renderer.
"""

from __future__ import annotations

from html.parser import HTMLParser

_SKIP_TAGS = frozenset({"script", "style", "noscript", "head", "svg"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def decode_bytes(content: bytes, content_type: str | None) -> str:
    """Pick a charset from the Content-Type header if present, otherwise
    assume UTF-8. Never raises - undecodable bytes are replaced, not
    dropped, so a byte-count-based size limit upstream stays meaningful.
    """
    charset = "utf-8"
    if content_type:
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip('"')
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def normalize_content(content: bytes, content_type: str | None) -> str:
    """Decode bytes using the declared/assumed charset, then strip HTML
    markup if the content type says this is HTML. Plain-text content
    types are returned decoded but otherwise untouched."""
    text = decode_bytes(content, content_type)
    if content_type and "html" in content_type.lower():
        return html_to_text(text)
    return text
