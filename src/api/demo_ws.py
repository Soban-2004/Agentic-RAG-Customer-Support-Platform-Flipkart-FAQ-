"""Anonymous simulation: ephemeral memory and session-local tool mutations."""

from fastapi import APIRouter, WebSocket
from src.api.chat_ws import serve_connection

router = APIRouter()


@router.websocket("/ws/demo")
async def demo_ws(websocket: WebSocket):
    await serve_connection(websocket)
