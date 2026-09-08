import pytest

from media.documents import UnsupportedDocumentTypeError, parse_document


def test_parse_txt() -> None:
    assert parse_document("log.txt", b"hello world") == "hello world"


def test_parse_json_pretty_prints() -> None:
    result = parse_document("config.json", b'{"a":1}')
    assert '"a": 1' in result


def test_parse_invalid_json_reports_error_but_returns_raw() -> None:
    result = parse_document("bad.json", b"{not json")
    assert "невалидный JSON" in result
    assert "{not json" in result


def test_parse_valid_yaml() -> None:
    result = parse_document("config.yaml", b"key: value")
    assert "key: value" in result


def test_parse_invalid_yaml_reports_error() -> None:
    result = parse_document("bad.yaml", b"key: [unterminated")
    assert "невалидный YAML" in result


def test_parse_xml() -> None:
    result = parse_document("data.xml", b"<root><item>1</item></root>")
    assert "<root>" in result


def test_parse_invalid_xml_reports_error() -> None:
    result = parse_document("bad.xml", b"<root><unclosed>")
    assert "невалидный XML" in result


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        parse_document("archive.zip", b"binary")


def test_long_document_is_truncated() -> None:
    result = parse_document("big.txt", b"x" * 100_000)
    assert "обрезано" in result
