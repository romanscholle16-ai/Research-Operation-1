from app.research.normalization import decode_bytes, html_to_text, normalize_content
from tests.research.conftest import SAMPLE_HTML


def test_html_to_text_strips_tags() -> None:
    text = html_to_text("<p>Hello <b>world</b></p>")
    assert "Hello" in text
    assert "world" in text
    assert "<p>" not in text
    assert "<b>" not in text


def test_html_to_text_removes_script_and_style_content() -> None:
    text = html_to_text(SAMPLE_HTML.decode("utf-8"))
    assert "should not appear" not in text
    assert "color:red" not in text
    assert "stop loss" in text.lower()


def test_decode_bytes_uses_declared_charset() -> None:
    content = "héllo".encode("latin-1")
    text = decode_bytes(content, "text/plain; charset=latin-1")
    assert text == "héllo"


def test_decode_bytes_defaults_to_utf8() -> None:
    content = "héllo".encode("utf-8")
    assert decode_bytes(content, None) == "héllo"


def test_decode_bytes_never_raises_on_bad_bytes() -> None:
    garbage = b"\xff\xfe\x00invalid"
    text = decode_bytes(garbage, "text/plain; charset=utf-8")
    assert isinstance(text, str)


def test_normalize_content_strips_html_for_html_content_type() -> None:
    text = normalize_content(SAMPLE_HTML, "text/html; charset=utf-8")
    assert "<html>" not in text
    assert "breakout" in text.lower()


def test_normalize_content_leaves_plain_text_untouched_besides_decoding() -> None:
    content = b"plain text content"
    text = normalize_content(content, "text/plain")
    assert text == "plain text content"
