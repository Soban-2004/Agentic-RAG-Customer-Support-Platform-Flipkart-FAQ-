"""Postgres is canonical; each turn gets a fresh bounded context projection."""

import uuid
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage


def build_session_memory(session_id: str, token_limit: int = 4000, messages=None):
    memory = ChatMemoryBuffer.from_defaults(token_limit=token_limit)
    if messages:
        memory.set(
            [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
        )
    return memory


def build_ephemeral_memory(token_limit: int = 4000):
    return build_session_memory(str(uuid.uuid4()), token_limit)
