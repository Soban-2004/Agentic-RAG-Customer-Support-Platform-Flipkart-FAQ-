"""Local immediate logout notification; database checks enforce revocation on all replicas."""

import asyncio
from src.api.security import decode_session

_sessions = {}


def register(token, websocket):
    claims = decode_session(token)
    if not claims:
        return None
    key = claims["jti"]
    _sessions.setdefault(key, set()).add(websocket)
    return key


def unregister(key, websocket):
    if key in _sessions:
        _sessions[key].discard(websocket)
        if not _sessions[key]:
            _sessions.pop(key, None)


async def close_session(token):
    claims = decode_session(token)
    if claims:
        sockets = _sessions.pop(claims["jti"], set())
        await asyncio.gather(
            *(ws.close(code=1008) for ws in sockets), return_exceptions=True
        )
