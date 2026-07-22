"""Process-wide singletons, set once by main.py's startup and read by
src/api/chat_ws.py. Safe to share across concurrent requests/connections:
`FunctionAgent` holds no per-user state (memory is passed per-call to
agent.run()), and `SemanticCache` is a stateless wrapper around a shared
Qdrant client -- see the migration plan's concurrency notes for why this is
an improvement over Chainlit's old per-connection rebuild, not a shortcut.
"""

from typing import Optional

from llama_index.core.agent.workflow import FunctionAgent

from src.gateway.cache import SemanticCache

agent: Optional[FunctionAgent] = None
cache: Optional[SemanticCache] = None
