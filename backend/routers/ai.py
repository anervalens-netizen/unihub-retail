"""
AI Router — WebSocket + HTTP proxy to Hermes Bridge (localhost:7777).

Endpoints:
  WS   /api/ai/ws             — streaming chat via WebSocket
  GET  /api/ai/health         — bridge health check
  GET  /api/ai/sessions       — list sessions for device
  POST /api/ai/sessions       — create new session
  GET  /api/ai/sessions/{id}  — session detail
  POST /api/ai/sessions/{id}/activate
  DELETE /api/ai/sessions/{id}
  POST /api/ai/attachments    — upload attachment
"""

from __future__ import annotations

import json
import logging
import os

import httpx
from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.websockets import WebSocketState

from models import AiAttachmentResponse, AiSessionDetailResponse, AiSessionListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

BRIDGE_URL = os.getenv("AI_BRIDGE_URL", "http://127.0.0.1:7777")
BRIDGE_TIMEOUT = float(os.getenv("AI_BRIDGE_TIMEOUT", "180"))

# Fixed user identifier used for Hermes bridge session partitioning now that
# auth has been removed. All sessions are scoped per device_id.
BRIDGE_USER_ID = "default"


async def _bridge_healthy() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BRIDGE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


@router.websocket("/ws")
async def ai_websocket(
    websocket: WebSocket,
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
    await websocket.accept()

    bridge_session_id = session_id
    if not bridge_session_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{BRIDGE_URL}/sessions/{BRIDGE_USER_ID}",
                    params={"device_id": device_id},
                )
                resp.raise_for_status()
                bridge_session_id = resp.json().get("active_session_id")
        except Exception:
            await websocket.send_json(
                {"type": "error", "message": "Nu s-a putut obține sesiunea AI."}
            )
            await websocket.close()
            return

    if not await _bridge_healthy():
        await websocket.send_json(
            {"type": "bridge_offline", "message": "UniAI nu este disponibil momentan."}
        )
        await websocket.close()
        return

    await websocket.send_json(
        {
            "type": "welcome",
            "message": "Bine ai venit! Sunt UniAI, asistentul tău de analiză vânzări.",
            "session_id": bridge_session_id,
        }
    )

    try:
        while True:
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

            await websocket.send_json({"type": "typing"})

            bridge_payload = {
                "message": content,
                "session_id": bridge_session_id,
                "user_id": BRIDGE_USER_ID,
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

                            raw_event = line[6:]
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
            except Exception:
                logger.exception("Bridge communication error")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Eroare internă de comunicare cu UniAI.",
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception:
        logger.exception("WebSocket error")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011)
            except Exception:
                pass


@router.get("/health")
async def ai_health():
    healthy = await _bridge_healthy()
    return {"online": healthy}


@router.get("/sessions", response_model=AiSessionListResponse)
async def ai_sessions(
    device_id: str = Query(..., min_length=6),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BRIDGE_URL}/sessions/{BRIDGE_USER_ID}",
                params={"device_id": device_id},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.get("/sessions/{session_id}", response_model=AiSessionDetailResponse)
async def ai_session_detail(session_id: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BRIDGE_URL}/sessions/{BRIDGE_USER_ID}/{session_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/sessions", response_model=AiSessionDetailResponse)
async def ai_create_session(
    device_id: str = Query(..., min_length=6),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BRIDGE_URL}/sessions",
                json={"user_id": BRIDGE_USER_ID, "device_id": device_id},
            )
            payload = resp.json()
            return {"session": payload["session"], "messages": payload["messages"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/sessions/{session_id}/activate", response_model=AiSessionDetailResponse)
async def ai_activate_session(
    session_id: str,
    device_id: str = Query(..., min_length=6),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BRIDGE_URL}/sessions/{session_id}/activate",
                json={"user_id": BRIDGE_USER_ID, "device_id": device_id},
            )
            payload = resp.json()
            return {"session": payload["session"], "messages": payload["messages"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.delete("/sessions/{session_id}")
async def ai_delete_session(session_id: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{BRIDGE_URL}/sessions/{session_id}",
                params={"user_id": BRIDGE_USER_ID},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Bridge error") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Bridge offline") from exc


@router.post("/attachments", response_model=AiAttachmentResponse)
async def ai_upload_attachment(
    file: UploadFile = File(...),
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
