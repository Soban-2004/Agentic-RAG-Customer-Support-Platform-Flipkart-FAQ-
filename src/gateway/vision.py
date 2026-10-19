"""
Vision sublayer of the AI Gateway -- describes a photo a user attaches to a
chat message (e.g. "my order arrived damaged, here's a photo") via Groq's
Llama 4 Scout, a natively multimodal model (config/models.yaml's `vision`
entry). Not routed through build_gateway_llm() -- same reasoning as
guardrails.py's prompt-injection check: a single-purpose call with no
fallback apparatus needed, not Settings.llm or the agent's own llm.

Output is a plain-text description folded into the normal turn as enrichment
(see chat_ws.py's _run_turn) -- not a separate tool the agent decides to
call. The WS protocol carries at most one image per message, so there's no
ambiguity about when to look at one; routing it through agent tool-calling
would just add a round-trip for a decision that's already made by the
client attaching a photo at all.
"""

import base64
import io
import warnings
from PIL import Image, UnidentifiedImageError
import logging
import os

import litellm
import yaml

logger = logging.getLogger("gateway.vision")

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "models.yaml"
)
_VISION_MODEL_KEY = "vision"

# Groq's own limit: base64-encoded image payloads are capped at 4MB (vs. 20MB
# for an image URL) -- console.groq.com/docs/vision. Measured against the
# base64 string length itself (what actually gets sent), not the decoded
# byte size, since that's what Groq's documented limit refers to.
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BASE64_BYTES = 4 * ((MAX_IMAGE_BYTES + 2) // 3)
MAX_IMAGE_PIXELS = 16_000_000
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

_DESCRIBE_PROMPT = (
    "This photo was attached to a Flipkart customer support message, most likely about a "
    "damaged, defective, or incorrect item. Describe factually what the photo shows: the "
    "product (if identifiable), and any visible damage, defect, missing parts, or discrepancy "
    "from what would be expected. Be concise (2-3 sentences), plain prose, no markdown. If the "
    "photo doesn't clearly show a product or damage, say so plainly rather than guessing."
)


class ImageTooLarge(Exception):
    pass


class UnsupportedImageType(Exception):
    pass


def _load_vision_entry() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    return config["models"][_VISION_MODEL_KEY]


def validate_image(image_base64: str, mime_type: str) -> None:
    """Raises ImageTooLarge/UnsupportedImageType/ValueError for a
    caller-facing rejection reason. Split out from describe_damage_photo so
    chat_ws.py can validate synchronously before spending a status frame /
    doing anything else, rather than discovering a bad payload only after
    starting the async describe call."""
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise UnsupportedImageType(f"Unsupported image type: {mime_type}")
    if len(image_base64) > MAX_IMAGE_BASE64_BYTES:
        raise ImageTooLarge(
            f"Image payload is {len(image_base64)} bytes, max is {MAX_IMAGE_BASE64_BYTES}"
        )
    try:
        decoded = base64.b64decode(image_base64, validate=True)
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ImageTooLarge("Decoded image exceeds 4 MiB")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(decoded)) as image:
                formats = {
                    "image/jpeg": "JPEG",
                    "image/png": "PNG",
                    "image/webp": "WEBP",
                }
                if (
                    image.format != formats[mime_type]
                    or image.width * image.height > MAX_IMAGE_PIXELS
                ):
                    raise ValueError(
                        "Image format or pixel dimensions are not permitted"
                    )
                image.verify()
    except Exception as e:
        raise ValueError("Malformed base64 image data") from e


async def describe_damage_photo(image_base64: str, mime_type: str) -> str:
    """Returns a plain-text description of the attached photo. Callers
    should call validate_image first; any failure here (Groq outage,
    unexpected response shape) should be caught broadly by the caller and
    degrade to processing the text message alone rather than failing the
    whole turn over a photo -- same fail-open philosophy as guardrails.py's
    prompt-injection check."""
    entry = _load_vision_entry()
    response = await litellm.acompletion(
        model=entry["model"],
        api_key=os.getenv(entry["api_key_env"]),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _DESCRIBE_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                    },
                ],
            }
        ],
        timeout=12,
        num_retries=0,
        temperature=0.2,
        max_tokens=200,
    )
    return response.choices[0].message.content or ""
