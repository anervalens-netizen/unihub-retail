"""
AI Router — WebSocket + HTTP proxy to Hermes Bridge (localhost:7777).

Endpoints:
  WS  /api/ai/ws?token=...   — streaming chat via WebSocket
  GET /api/ai/health          — bridge health check
  POST /api/ai/reset          — reset conversation session
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.websockets import WebSocketState

from dependencies import get_current_user
from models import AiAttachmentResponse, AiSessionDetailResponse, AiSessionListResponse
from services.auth_service import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

BRIDGE_URL = os.getenv("AI_BRIDGE_URL", "http://127.0.0.1:7777")
BRIDGE_TIMEOUT = float(os.getenv("AI_BRIDGE_TIMEOUT", "180"))  # seconds — generous for complex AI queries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _bridge_healthy() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BRIDGE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _validate_ws_token(token: str) -> dict[str, Any]:
    """Validate JWT token for WebSocket (no Bearer header available in WS)."""
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token invalid") from exc

    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, role, full_name, is_active FROM users WHERE id = $1",
            int(payload["user_id"]),
        )
    if row is None or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Utilizator inactiv")
    return dict(row)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def ai_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    device_id: str = Query(..., min_length=6),
    session_id: str | None = Query(None),
):
    """
    WebSocket chat endpoint.

    Protocol:
      Client → Server: {"type": "message", "content": "...", "reset": false}
      Server → Client: {"type": "typing"}
      Server → Client: {"type": "tool_use", "name": "...", "input": "..."}
      Server → Client: {"type": "token", "content": "..."}
      Server → Client: {"type": "done"}
      Server → Client: {"type": "error", "message": "..."}
      Server → Client: {"type": "bridge_offline"}
    """
    # Validate token before accepting
    try:
        user = await _validate_ws_token(token)
    except HTTPException:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    bridge_session_id = session_id
    if not bridge_session_id:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BRIDGE_URL}/sessions/{user['id']}",
                params={"device_id": device_id},
            )
            resp.raise_for_status()
            bridge_session_id = resp.json()["active_session_id"]

    # Check bridge availability
    if not await _bridge_healthy():
        await websocket.send_json(
            {"type": "bridge_offline", "message": "UniAI nu este disponibil momentan."}
        )
        await websocket.close()
        return

    # Send welcome
    await websocket.send_json(
        {
            "type": "welcome",
            "message": f"Bine ai venit, {user.get('full_name') or user['username']}! Sunt UniAI, asistentul tău de analiză vânzări.",
            "session_id": bridge_session_id,
        }
    )

    try:
        while True:
            # Wait for user message
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Format mesaj invalid."}
                )
                continue

            content = msg.get("content", "").strip()
            if not content:
                continue

            reset = bool(msg.get("reset", False))

            # Send typing indicator
            await websocket.send_json({"type": "typing"})

            # Stream from bridge
            bridge_payload = {
                "message": content,
                "session_id": bridge_session_id,
                "user_id": str(user["id"]),
                "reset": reset,
                "attachments": msg.get("attachments", []),
            }

            try:
                async with httpx.AsyncClient(timeout=BRIDGE_TIMEOUT) as client:
                    async with client.stream(
                        "POST",
                        f"{BRIDGE_URL}/chat",
                        json=bridge_payload,
                        headers={"Accept": "text/event-stream"},
                    ) as response:
                        if response.status_code != 200:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Eroare bridge: HTTP {response.status_code}",
                                }
                            )
                            continue

                        async for line in response.aiter_lines():
                            if websocket.client_state == WebSocketState.DISCONNECTED:
                                break

                            if not line.startswith("data: "):
                                continue

                            raw_event = line[6:]  # strip "data: "
                            try:
                                event = json.loads(raw_event)
                            except json.JSONDecodeError:
                                continue

                            event_type = event.get("type")

                            if event_type == "token":
                                await websocket.send_json(event)

                            elif event_type == "tool_start":
                                await websocket.send_json(
                                    {
                                        "type": "tool_use",
                                        "name": event.get("name", ""),
                                        "input": event.get("input", ""),
                                    }
                                )

                            elif event_type == "tool_done":
                                # Don't forward tool results — too verbose
                                pass

                            elif event_type == "done":
                                await websocket.send_json({"type": "done"})

                            elif event_type == "error":
                                await websocket.send_json(event)

            except httpx.TimeoutException:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Timeout: UniAI nu a răspuns în timp util.",
                    }
                )
            except httpx.ConnectError:
                await websocket.send_json(
                    {
                        "type": "bridge_offline",
                        "message": "UniAI nu este disponibil momentan.",
                    }
                )
            except Exception as exc:
                logger.exception(
                    "Bridge communication error for user %s", user["username"]
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Eroare internă de comunicare cu UniAI.",
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s", user["username"])
    except Exception as exc:
        logger.exception("WebSocket error for user %s", user["username"])
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
async def ai_health(user: dict[str, Any] = Depends(get_current_user)):
    """Check if the AI bridge is online."""
    healthy = await _bridge_healthy()
    return {"online": healthy, "bridge_url": BRIDGE_URL}


@router.get("/sessions", response_model=AiSessionListResponse)
async def ai_sessions(
    device_id: str = Query(..., min_length=6),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BRIDGE_URL}/sessions/{user['id']}",
                params={"device_id": device_id},
            )
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.get("/sessions/{session_id}", response_model=AiSessionDetailResponse)
async def ai_session_detail(
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BRIDGE_URL}/sessions/{user['id']}/{session_id}")
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/sessions", response_model=AiSessionDetailResponse)
async def ai_create_session(
    device_id: str = Query(..., min_length=6),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BRIDGE_URL}/sessions",
                json={"user_id": str(user["id"]), "device_id": device_id},
            )
            payload = resp.json()
            return {"session": payload["session"], "messages": payload["messages"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/sessions/{session_id}/activate", response_model=AiSessionDetailResponse)
async def ai_activate_session(
    session_id: str,
    device_id: str = Query(..., min_length=6),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BRIDGE_URL}/sessions/{session_id}/activate",
                json={"user_id": str(user["id"]), "device_id": device_id},
            )
            payload = resp.json()
            return {"session": payload["session"], "messages": payload["messages"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/attachments", response_model=AiAttachmentResponse)
async def ai_upload_attachment(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        files = {
            "file": (
                file.filename or "attachment",
                await file.read(),
                file.content_type or "application/octet-stream",
            )
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{BRIDGE_URL}/attachments", files=files)
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc
