import base64
from typing import Any


def build_image_content_block(image_bytes: bytes, media_type: str = "image/jpeg") -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": encoded},
    }


def build_text_content_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}
