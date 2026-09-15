from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

from runtime_config import _is_production

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STORAGE_ROOT = _REPO_ROOT / "data" / "ai-assistant"

AI_RUNTIME_URL_ENV = "AI_ASSISTANT_RUNTIME_URL"
AI_STORAGE_ROOT_ENV = "AI_ASSISTANT_STORAGE_ROOT"
AI_SNAPSHOT_ROOT_ENV = "AI_ASSISTANT_SNAPSHOT_ROOT"
AI_SANDBOX_IMAGE_ENV = "AI_ASSISTANT_SANDBOX_IMAGE"
AI_READONLY_DSN_ENV = "AI_ASSISTANT_READONLY_DSN"
AI_GUARD_DSN_ENV = "AI_ASSISTANT_GUARD_DSN"
AI_MAX_CONCURRENT_RUNS_ENV = "AI_ASSISTANT_MAX_CONCURRENT_RUNS_PER_OWNER"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
AI_MODEL = "gpt-5.6-luna"

# Capability-first default: one owner may hold two sandboxes at once. This is a
# mathematical bound on Docker/model spend, not a normal-use policy.
AI_MAX_CONCURRENT_RUNS_PER_OWNER = 2
_AI_MAX_CONCURRENT_RUNS_CEILING = 16


@dataclass(frozen=True, slots=True)
class AiAssistantSettings:
    model: str
    runtime_url: str
    storage_root: Path
    snapshot_root: Path
    knowledge_root: Path
    sandbox_image: str
    max_artifact_bytes: int
    setup_timeout_seconds: int
    # Never render the sandbox credential: it is resolved into the model
    # sandbox environment and must not appear in logs or tracebacks.
    readonly_dsn: str = field(default="", repr=False)
    # Host-only watchdog credential: never resolve into sandbox environment.
    guard_dsn: str = field(default="", repr=False)
    max_concurrent_runs_per_owner: int = AI_MAX_CONCURRENT_RUNS_PER_OWNER
    max_total_artifact_bytes: int = 1024 * 1024 * 1024


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1024 * 1024:
        raise RuntimeError(f"{name} must be at least 1 MiB")
    return value


def _bounded_seconds(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 5 or value > 300:
        raise RuntimeError(f"{name} must be between 5 and 300 seconds")
    return value


def _bounded_runs_per_owner() -> int:
    raw = os.getenv(AI_MAX_CONCURRENT_RUNS_ENV, str(AI_MAX_CONCURRENT_RUNS_PER_OWNER)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{AI_MAX_CONCURRENT_RUNS_ENV} must be an integer") from exc
    if value < 1 or value > _AI_MAX_CONCURRENT_RUNS_CEILING:
        raise RuntimeError(
            f"{AI_MAX_CONCURRENT_RUNS_ENV} must be between 1 and "
            f"{_AI_MAX_CONCURRENT_RUNS_CEILING}"
        )
    return value


def _validated_loopback_runtime_url(raw: str) -> str:
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError(f"{AI_RUNTIME_URL_ENV} is invalid") from exc
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        raise RuntimeError(f"{AI_RUNTIME_URL_ENV} must be an unauthenticated loopback HTTP URL")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"{AI_RUNTIME_URL_ENV} must be loopback-only")
    if port is None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError(f"{AI_RUNTIME_URL_ENV} must contain only loopback host and port")
    return raw.rstrip("/")


def _validate_sandbox_readonly_dsn(raw: str) -> None:
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise RuntimeError(f"{AI_READONLY_DSN_ENV} must be a valid PostgreSQL DSN") from exc
    if parsed.scheme not in {"postgresql", "postgres"} or not host:
        raise RuntimeError(f"{AI_READONLY_DSN_ENV} must be a PostgreSQL DSN")
    normalized = host.casefold()
    if normalized == "localhost":
        raise RuntimeError(
            f"{AI_READONLY_DSN_ENV} must use a database host reachable from the Docker sandbox, not localhost"
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_unspecified:
        raise RuntimeError(
            f"{AI_READONLY_DSN_ENV} must use a database host reachable from the Docker sandbox, not loopback"
        )


def _validate_guard_dsn(raw: str) -> None:
    try:
        parsed = urlsplit(raw)
        valid = (parsed.scheme in {"postgresql", "postgres"} and parsed.hostname
                 and parsed.username == "unihub_ai_guard" and parsed.port
                 and parsed.path not in {"", "/"} and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError(
            f"{AI_GUARD_DSN_ENV} must be a direct unihub_ai_guard PostgreSQL DSN "
            "with explicit host, port and database and no connection overrides"
        )


def load_ai_assistant_settings(*, runtime: bool = False) -> AiAssistantSettings:
    storage_default = (
        Path("/var/lib/unihub-retail/ai-assistant")
        if _is_production()
        else _DEFAULT_STORAGE_ROOT
    )
    storage_root = Path(
        os.getenv(AI_STORAGE_ROOT_ENV, str(storage_default))
    ).expanduser().resolve()
    snapshot_root = Path(
        os.getenv(AI_SNAPSHOT_ROOT_ENV, str(storage_root / "snapshots"))
    ).expanduser().resolve()
    runtime_url = _validated_loopback_runtime_url(
        os.getenv(AI_RUNTIME_URL_ENV, "http://127.0.0.1:9911").strip()
    )
    readonly_dsn = ""
    guard_dsn = ""
    if runtime:
        if not os.getenv(OPENAI_API_KEY_ENV, "").strip():
            raise RuntimeError(f"{OPENAI_API_KEY_ENV} is required by the AI runtime")
        readonly_dsn = os.getenv(AI_READONLY_DSN_ENV, "").strip()
        _validate_sandbox_readonly_dsn(readonly_dsn)
        guard_dsn = os.getenv(AI_GUARD_DSN_ENV, "").strip()
        _validate_guard_dsn(guard_dsn)
    settings = AiAssistantSettings(
        model=AI_MODEL,
        runtime_url=runtime_url,
        storage_root=storage_root,
        snapshot_root=snapshot_root,
        knowledge_root=Path(__file__).resolve().parent / "knowledge",
        sandbox_image=os.getenv(
            AI_SANDBOX_IMAGE_ENV, "unihub-retail-ai-sandbox:v3-dev"
        ).strip(),
        max_artifact_bytes=_positive_int(
            "AI_ASSISTANT_MAX_ARTIFACT_BYTES", 256 * 1024 * 1024
        ),
        setup_timeout_seconds=_bounded_seconds("AI_ASSISTANT_SETUP_TIMEOUT_SECONDS", 90),
        readonly_dsn=readonly_dsn,
        guard_dsn=guard_dsn,
        max_concurrent_runs_per_owner=_bounded_runs_per_owner(),
        max_total_artifact_bytes=_positive_int(
            "AI_ASSISTANT_MAX_TOTAL_ARTIFACT_BYTES", 1024 * 1024 * 1024
        ),
    )
    if settings.max_total_artifact_bytes < settings.max_artifact_bytes:
        raise RuntimeError(
            "AI_ASSISTANT_MAX_TOTAL_ARTIFACT_BYTES must be at least "
            "AI_ASSISTANT_MAX_ARTIFACT_BYTES"
        )
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.snapshot_root.mkdir(parents=True, exist_ok=True)
    return settings


def resolve_storage_key(storage_root: Path, storage_key: str) -> Path:
    candidate = (storage_root / storage_key).resolve()
    if not candidate.is_relative_to(storage_root):
        raise ValueError("artifact storage path escapes AI storage root")
    return candidate
