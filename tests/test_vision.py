import base64

from ai.vision import build_image_content_block, build_text_content_block


def test_build_image_content_block_encodes_base64() -> None:
    block = build_image_content_block(b"fake-image-bytes", media_type="image/jpeg")
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(block["source"]["data"]) == b"fake-image-bytes"


def test_build_text_content_block() -> None:
    block = build_text_content_block("hello")
    assert block == {"type": "text", "text": "hello"}
