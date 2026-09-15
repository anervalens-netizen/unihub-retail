from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ai_assistant.runtime import AiSandboxRuntime
from schemas.ai_assistant import RuntimeSteerRequest, RuntimeTurnRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ai_runtime = AiSandboxRuntime()
    yield


app = FastAPI(
    title="UniHub AI Runtime",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def _runtime(request: Request) -> AiSandboxRuntime:
    runtime = getattr(request.app.state, "ai_runtime", None)
    if not isinstance(runtime, AiSandboxRuntime):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI runtime unavailable")
    return runtime


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/ai/run")
async def run_turn(payload: RuntimeTurnRequest, request: Request) -> StreamingResponse:
    return StreamingResponse(
        _runtime(request).stream_turn(payload),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/internal/ai/{conversation_id}/steer")
async def steer(
    conversation_id: UUID,
    payload: RuntimeSteerRequest,
    request: Request,
) -> dict[str, bool]:
    try:
        await _runtime(request).steer(conversation_id, payload)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"accepted": True}


@app.post("/internal/ai/{conversation_id}/stop")
async def stop(conversation_id: UUID, request: Request) -> dict[str, bool]:
    try:
        await _runtime(request).stop(conversation_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"ok": True}
