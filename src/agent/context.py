"""Trusted execution context, never part of model-controlled tool schemas."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class ToolContext:
    actor_id: str
    thread_id: str
    turn_id: str
    session_token: str | None = None
    demo: bool = False
    read_only: bool = False
    demo_state: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)


_current = ContextVar("trusted_tool_context", default=None)


def current_context():
    context = _current.get()
    if context is None:
        raise PermissionError("Authenticated tool execution context is required")
    return context


@contextmanager
def tool_context(context):
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)
