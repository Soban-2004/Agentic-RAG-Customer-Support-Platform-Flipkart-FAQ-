"""
Qdrant client factory: switches between a self-hosted/cloud server and an
embedded local (file-on-disk) instance based on whether QDRANT_URL is set.

Local mode needs zero infrastructure (no account, no Docker, no free-tier
cluster limits) but qdrant-client enforces a hard rule: a local storage
folder can only be opened by ONE client at a time, sync or async, in one
process. Concretely that means:
  - Within the running app, use ONLY get_async_qdrant_client() -- never open
    a second (sync) client on the same path while the app is running.
  - Don't run an offline script (e.g. src/ingestion/embed_qdrant.py) against
    the same local path while the app is running; stop the app first.
Switching QDRANT_URL (+ QDRANT_API_KEY) back on in .env removes both
restrictions by pointing everything at a real Qdrant server instead.
"""

import os
from pathlib import Path

import qdrant_client

DEFAULT_LOCAL_PATH = str(Path(__file__).resolve().parent.parent.parent / "qdrant_storage")


def _local_path() -> str:
    return os.getenv("QDRANT_LOCAL_PATH", DEFAULT_LOCAL_PATH)


def is_remote() -> bool:
    return bool(os.getenv("QDRANT_URL"))


def get_async_qdrant_client() -> qdrant_client.AsyncQdrantClient:
    if is_remote():
        return qdrant_client.AsyncQdrantClient(
            url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY")
        )
    return qdrant_client.AsyncQdrantClient(path=_local_path())


def get_sync_qdrant_client(timeout: int = 60) -> qdrant_client.QdrantClient:
    """For standalone/offline scripts only (see module docstring)."""
    if is_remote():
        return qdrant_client.QdrantClient(
            url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"), timeout=timeout
        )
    return qdrant_client.QdrantClient(path=_local_path())
