import io
import json

import yaml
from defusedxml import ElementTree
from pypdf import PdfReader

MAX_DOCUMENT_CHARS = 50_000


def _parse_text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def _parse_json(content: bytes) -> str:
    text = _parse_text(content)
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        return f"[невалидный JSON: {exc}]\n{text}"


def _parse_yaml(content: bytes) -> str:
    text = _parse_text(content)
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return f"[невалидный YAML: {exc}]\n{text}"
    return text


def _parse_xml(content: bytes) -> str:
    text = _parse_text(content)
    try:
        ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return f"[невалидный XML: {exc}]\n{text}"
    return text


def _parse_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


PARSERS = {
    ".txt": _parse_text,
    ".log": _parse_text,
    ".json": _parse_json,
    ".yaml": _parse_yaml,
    ".yml": _parse_yaml,
    ".xml": _parse_xml,
    ".pdf": _parse_pdf,
}


class UnsupportedDocumentTypeError(Exception):
    pass


def parse_document(filename: str, content: bytes) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    parser = PARSERS.get(ext)
    if parser is None:
        raise UnsupportedDocumentTypeError(f"Unsupported document type: {ext or filename!r}")

    text = parser(content)
    if len(text) > MAX_DOCUMENT_CHARS:
        text = text[:MAX_DOCUMENT_CHARS] + "\n[...обрезано...]"
    return text
