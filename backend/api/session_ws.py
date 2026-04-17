import asyncio
import hashlib
from urllib.parse import urlencode

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.orm import Session

from config import get_settings
from db.database import SessionLocal
from db.models import SessionStatus, WorkspaceSession

router = APIRouter(tags=["session-ws"])
settings = get_settings()


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256((settings.session_cookie_domain or "local").encode() + ticket.encode()).hexdigest()


def _load_session(db: Session, session_id: str) -> WorkspaceSession | None:
    return db.get(WorkspaceSession, session_id)


@router.websocket("/ws/session/{session_id}")
async def session_ws_proxy(websocket: WebSocket, session_id: str) -> None:
    async def _safe_close(code: int, reason: str) -> None:
        if websocket.client_state == WebSocketState.DISCONNECTED:
            return
        try:
            await websocket.close(code=code, reason=reason)
        except RuntimeError:
            # Starlette raises if close is attempted after connection completion.
            return

    await websocket.accept()
    ticket = websocket.cookies.get("session_ticket")
    if not ticket:
        await _safe_close(code=4401, reason="Missing session ticket")
        return

    db = SessionLocal()
    try:
        ws = _load_session(db, session_id)
        if ws is None:
            await _safe_close(code=4404, reason="Session not found")
            return
        if ws.status not in (SessionStatus.RUNNING, SessionStatus.PAUSED):
            await _safe_close(code=4400, reason="Session not active")
            return
        if not ws.internal_ip or not ws.vnc_port:
            await _safe_close(code=4400, reason="Session endpoint unavailable")
            return
        if not ws.session_token_hash or _ticket_hash(ticket) != ws.session_token_hash:
            await _safe_close(code=4401, reason="Invalid session ticket")
            return
    finally:
        db.close()

    target = f"ws://{ws.internal_ip}:{ws.vnc_port}{settings.container_vnc_ws_path}"
    query = websocket.query_params.multi_items()
    if query:
        target = f"{target}?{urlencode(query)}"

    try:
        async with websockets.connect(target, max_size=None) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if "bytes" in message and message["bytes"] is not None:
                        await upstream.send(message["bytes"])
                    elif "text" in message and message["text"] is not None:
                        await upstream.send(message["text"])
                    elif message.get("type") == "websocket.disconnect":
                        break

            async def upstream_to_client() -> None:
                while True:
                    payload = await upstream.recv()
                    if isinstance(payload, bytes):
                        await websocket.send_bytes(payload)
                    else:
                        await websocket.send_text(payload)

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        return
    except Exception:
        await _safe_close(code=1011, reason="Upstream proxy error")
