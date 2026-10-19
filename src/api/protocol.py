"""Bounded transport envelopes, validated before storage or provider calls."""

import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.api.settings import settings


class ImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    data: str = Field(min_length=1, max_length=5_592_408)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    content: str = Field(default="", max_length=16000)
    image: ImageInput | None = None
    client_message_id: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    regenerate_message_id: str | None = Field(
        default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$"
    )

    @model_validator(mode="after")
    def nonempty(self):
        self.content = self.content.strip()
        if not self.content and self.image is None:
            raise ValueError("A message or image is required")
        return self


def parse_frame(raw):
    if len(raw.encode("utf-8")) > settings().max_frame_bytes:
        raise ValueError("Message exceeds the transport size limit")
    data = json.loads(raw)
    return ChatInput.model_validate(data)
