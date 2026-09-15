from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from runtime_config import _is_production

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STORAGE_ROOT = _REPO_ROOT / "data" / "ai-assistant"

AI_RUNTIME_URL_ENV = "AI_ASSISTANT_RUNTIME_URL"
AI_STORAGE_ROOT_ENV = "AI_ASSISTANT_STORAGE_ROOT"
AI_SNAPSHOT_ROOT_ENV = "AI_ASSISTANT_SNAPSHOT_ROOT"
AI_SANDBOX_IMAGE_ENV = "AI_ASSISTANT_SANDBOX_IMAGE"
AI_READONLY_DSN_ENV = "AI_ASSISTANT_READONLY_DSN"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
AI_MODEL = "gpt-5.6-luna"


@dataclass(frozen=True, slots=True)
class AiAssistantSettings:
    model: str
    runtime_url: str
    storage_root: Path
    snapshot_root: Path
    knowledge_root: Path
    sandbox_image: str
    max_artifact_bytes: int


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1024 * 1024:
        raise RuntimeError(f"{name} must be at least 1 MiB")
    return value


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
    runtime_url = os.getenv(
        AI_RUNTIME_URL_ENV, "http://127.0.0.1:9911"
    ).strip().rstrip("/")
    if not runtime_url.startswith(
        ("http://127.0.0.1:", "http://localhost:", "http://[::1]:")
    ):
        raise RuntimeError(f"{AI_RUNTIME_URL_ENV} must be loopback-only")
    if runtime:
        if not os.getenv(OPENAI_API_KEY_ENV, "").strip():
            raise RuntimeError(f"{OPENAI_API_KEY_ENV} is required by the AI runtime")
        readonly_dsn = os.getenv(AI_READONLY_DSN_ENV, "").strip()
        if not readonly_dsn.startswith(("postgresql://", "postgres://")):
            raise RuntimeError(f"{AI_READONLY_DSN_ENV} must be a PostgreSQL DSN")
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
    )
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.snapshot_root.mkdir(parents=True, exist_ok=True)
    return settings


def resolve_storage_key(storage_root: Path, storage_key: str) -> Path:
    candidate = (storage_root / storage_key).resolve()
    if not candidate.is_relative_to(storage_root):
        raise ValueError("artifact storage path escapes AI storage root")
    return candidate
