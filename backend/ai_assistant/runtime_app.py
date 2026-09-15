from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from ai_assistant.runtime import AiSandboxRuntime
from schemas.ai_assistant import RuntimeSteerRequest, RuntimeTurnRequest

_AUTHORITY_UNVERIFIED = (
    "AI read-only database authority is not verified; refusing to expose the sandbox credential"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = AiSandboxRuntime()
    app.state.ai_runtime = runtime
    try:
        await runtime.verify_readonly_authority()
    except Exception:
        # Fail closed but stay observable: the process keeps serving /health as
        # 503 with the rejection reason and refuses every run until a restart
        # re-runs the preflight successfully.
        pass
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
async def health(request: Request) -> JSONResponse:
    """Report healthy only after the sandbox credential proved read-only."""
    runtime = _runtime(request)
    if not runtime.authority_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unavailable",
                "reason": runtime.authority_error or _AUTHORITY_UNVERIFIED,
            },
        )
    return JSONResponse({"status": "ok"})


@app.post("/internal/ai/run")
async def run_turn(payload: RuntimeTurnRequest, request: Request) -> StreamingResponse:
    runtime = _runtime(request)
    if not runtime.authority_ready:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _AUTHORITY_UNVERIFIED)
    return StreamingResponse(
        runtime.stream_turn(payload),
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
