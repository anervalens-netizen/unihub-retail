from __future__ import annotations

import json
from typing import Any, AsyncIterator, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import httpx

from auth import AuthClaims, require_auth
from composition import build_ai_assistant_service
from permissions import can_access_management, require_privileged_access
from privileged_access import STORE_PNL_ACCESS_GROUPS_ENV, has_configured_group
from rate_limits import AI_TURN_LIMIT, rate_limit
from schemas.ai_assistant import (
    AiConversationCreate,
    AiMessageItem,
    AiConversationItem,
    AiConversationListResponse,
    AiMessageListResponse,
    AiReasoningEffort,
    AiSteerResponse,
    AiStopResponse,
    RUNTIME_ADMISSION_REJECTION_MESSAGE,
    RuntimeCompleteEvent,
    RuntimeSteerRequest,
    RuntimeTurnRequest,
)
from services.ai_assistant import AiArtifactNotFound, AiAssistantService, AiConversationNotFound

router = APIRouter(prefix="/api/ai", tags=["ai-assistant"])
get_ai_service = build_ai_assistant_service
_STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0)
_CONTROL_TIMEOUT = httpx.Timeout(15.0)


def can_access_ai_assistant(claims: AuthClaims) -> bool:
    return can_access_management(claims) and has_configured_group(
        claims.groups, STORE_PNL_ACCESS_GROUPS_ENV
    )


def require_ai_owner(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return require_privileged_access(
        request=request,
        claims=claims,
        allowed=can_access_ai_assistant(claims),
        resource="ai_assistant",
        detail="UniHub AI este disponibil numai proprietarului autorizat.",
        fallback_route="/api/ai",
    )


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "AI conversation not found")


def _parse_current_view(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    if len(raw) > 64 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI current-view context is too large")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI current-view context is invalid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI current-view context must be an object")
    return value


def _line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


async def _record_runtime_error(
    service: AiAssistantService,
    owner_subject: str,
    conversation_id: UUID,
    message: str,
) -> None:
    try:
        await service.record_error_message(owner_subject, conversation_id, message)
    except Exception:
        # Transport failure must remain visible to the caller even if durable
        # error bookkeeping itself fails.
        return


@router.get("/conversations", response_model=AiConversationListResponse)
async def list_conversations(
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> AiConversationListResponse:
    return AiConversationListResponse(items=await service.list_conversations(claims.sub))


@router.post(
    "/conversations",
    response_model=AiConversationItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: AiConversationCreate,
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> AiConversationItem:
    return await service.create_conversation(claims.sub, payload.effort)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=AiMessageListResponse,
)
async def list_messages(
    conversation_id: UUID,
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> AiMessageListResponse:
    try:
        items = await service.list_messages(claims.sub, conversation_id)
    except AiConversationNotFound as exc:
        raise _not_found() from exc
    return AiMessageListResponse(items=items)


async def _stream_runtime_events(
    *,
    service: AiAssistantService,
    owner_subject: str,
    conversation_id: UUID,
    runtime_url: str,
    payload: RuntimeTurnRequest,
    user_message: AiMessageItem,
) -> AsyncIterator[bytes]:
    """Proxy one accepted run to the browser while persisting its outcome."""
    yield _line({"type": "user_message", "message": user_message.model_dump(mode="json")})
    try:
        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                runtime_url,
                json=payload.model_dump(mode="json"),
            ) as response:
                if response.status_code != status.HTTP_200_OK:
                    detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    message = detail or "AI runtime unavailable"
                    await _record_runtime_error(service, owner_subject, conversation_id, message)
                    yield _line({"type": "error", "message": message})
                    return
                async for raw_line in response.aiter_lines():
                    if not raw_line:
                        continue
                    try:
                        event = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "error":
                        message = str(event.get("message") or "UniHub AI nu a putut finaliza cererea.")
                        if message == RUNTIME_ADMISSION_REJECTION_MESSAGE:
                            try:
                                await service.compensate_rejected_submission(
                                    owner_subject, conversation_id, user_message.id,
                                )
                            except Exception:
                                message = "Nu am putut anula salvarea cererii AI respinse."
                            yield _line({"type": "error", "message": message})
                            return
                        await _record_runtime_error(service, owner_subject, conversation_id, message)
                        yield _line({"type": "error", "message": message})
                        continue
                    if event.get("type") != "complete":
                        yield _line(event)
                        continue
                    completed = RuntimeCompleteEvent.model_validate(event)
                    assistant_message = await service.finish_assistant_message(
                        owner_subject,
                        conversation_id,
                        text=completed.text,
                        previous_response_id=completed.previous_response_id,
                        artifacts=completed.artifacts,
                    )
                    yield _line(
                        {
                            "type": "complete",
                            "message": assistant_message.model_dump(mode="json"),
                            "previous_response_id": completed.previous_response_id,
                        }
                    )
    except httpx.HTTPError:
        message = "UniHub AI runtime nu este disponibil."
        await _record_runtime_error(service, owner_subject, conversation_id, message)
        yield _line({"type": "error", "message": message})


@router.post(
    "/conversations/{conversation_id}/turn",
    dependencies=[Depends(rate_limit(AI_TURN_LIMIT))],
)
async def run_turn(
    conversation_id: UUID,
    request: Request,
    text: str = Form(default="", max_length=50_000),
    effort: AiReasoningEffort = Form(default="high"),
    current_view: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> StreamingResponse:
    del request
    resolved_files = files or []
    if not text.strip() and not resolved_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI turn requires text or a file")
    parsed_current_view = _parse_current_view(current_view)
    try:
        user_message, uploads, previous_response_id, _ = await service.begin_user_message(
            claims.sub,
            conversation_id,
            text=text,
            effort=effort,
            files=resolved_files,
        )
    except AiConversationNotFound as exc:
        raise _not_found() from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc

    payload = RuntimeTurnRequest(
        conversation_id=conversation_id,
        owner_subject=claims.sub,
        text=text,
        effort=effort,
        previous_response_id=previous_response_id,
        current_view=parsed_current_view,
        uploads=uploads,
    )
    return StreamingResponse(
        _stream_runtime_events(
            service=service,
            owner_subject=claims.sub,
            conversation_id=conversation_id,
            runtime_url=f"{service.settings.runtime_url}/internal/ai/run",
            payload=payload,
            user_message=user_message,
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/conversations/{conversation_id}/steer",
    response_model=AiSteerResponse,
)
async def steer(
    conversation_id: UUID,
    text: str = Form(default="", max_length=50_000),
    current_view: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> AiSteerResponse:
    resolved_files = files or []
    if not text.strip() and not resolved_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI steer requires text or a file")
    parsed_current_view = _parse_current_view(current_view)
    try:
        conversation = await service.require_conversation(claims.sub, conversation_id)
        effort = cast(AiReasoningEffort, conversation["effort"])
        user_message, uploads, _, order_key = await service.begin_user_message(
            claims.sub,
            conversation_id,
            text=text,
            effort=effort,
            files=resolved_files,
            steer=True,
        )
    except AiConversationNotFound as exc:
        raise _not_found() from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    payload = RuntimeSteerRequest(
        text=text,
        order_key=order_key,
        current_view=parsed_current_view,
        uploads=uploads,
    )
    try:
        async with httpx.AsyncClient(timeout=_CONTROL_TIMEOUT) as client:
            response = await client.post(
                f"{service.settings.runtime_url}/internal/ai/{conversation_id}/steer",
                json=payload.model_dump(mode="json"),
            )
            if response.status_code == status.HTTP_409_CONFLICT:
                try:
                    await service.compensate_rejected_submission(claims.sub, conversation_id, user_message.id)
                except Exception as exc:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "AI Steer a fost refuzat, dar anularea salvării sau curățarea fișierelor a eșuat.",
                    ) from exc
                raise HTTPException(status.HTTP_409_CONFLICT, "Nu există un run AI activ care poate fi ghidat.")
            if response.status_code != status.HTTP_200_OK:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "UniHub AI runtime nu este disponibil.")
    except httpx.HTTPError as exc:
        message = "UniHub AI runtime nu este disponibil."
        await _record_runtime_error(service, claims.sub, conversation_id, message)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, message) from exc
    return AiSteerResponse(accepted=True, message=user_message)


@router.post(
    "/conversations/{conversation_id}/stop",
    response_model=AiStopResponse,
)
async def stop(
    conversation_id: UUID,
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> AiStopResponse:
    try:
        await service.require_conversation(claims.sub, conversation_id)
    except AiConversationNotFound as exc:
        raise _not_found() from exc
    try:
        async with httpx.AsyncClient(timeout=_CONTROL_TIMEOUT) as client:
            response = await client.post(
                f"{service.settings.runtime_url}/internal/ai/{conversation_id}/stop"
            )
            if response.status_code != status.HTTP_200_OK:
                raise HTTPException(status.HTTP_409_CONFLICT, "Nu există un run AI activ de oprit.")
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "UniHub AI runtime nu este disponibil.") from exc
    return AiStopResponse(ok=True)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: UUID,
    claims: AuthClaims = Depends(require_ai_owner),
    service: AiAssistantService = Depends(get_ai_service),
) -> FileResponse:
    try:
        path, filename, mime_type = await service.artifact_path(claims.sub, artifact_id)
    except AiArtifactNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AI artifact not found") from exc
    return FileResponse(path, filename=filename, media_type=mime_type)
