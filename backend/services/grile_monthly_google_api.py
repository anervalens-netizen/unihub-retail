"""Google credential and retry boundary for monthly Grile operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def service_account_file(api: Any) -> Path:
    default = api.BASE_DIR / "config" / "google" / "service-account.json"
    return Path(api.os.getenv("GRILE_GOOGLE_SA_FILE", default))


def credentials(api: Any) -> Any:
    from google.oauth2.service_account import Credentials

    path = api._sa_file()
    if not path.exists():
        raise FileNotFoundError(
            f"Service account Google lipsa: {path}. "
            "Pune fisierul sau seteaza GRILE_GOOGLE_SA_FILE."
        )
    return Credentials.from_service_account_file(str(path), scopes=api.SCOPES)


def build_services(api: Any) -> tuple[Any, Any]:
    creds = api.get_credentials()
    return (
        api.build("sheets", "v4", credentials=creds, cache_discovery=False),
        api.build("drive", "v3", credentials=creds, cache_discovery=False),
    )


def is_transient(api: Any, exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in api._TRANSIENT


def error_code(api: Any, exc: Exception) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 429:
        return "google_rate_limited"
    if status in {500, 502, 503, 504}:
        return "google_unavailable"
    if isinstance(exc, (TimeoutError, api.asyncio.TimeoutError)):
        return "google_timeout"
    return "google_request_failed"


def retry(
    api: Any,
    fn: Any,
    *,
    label: str,
    attempts: int = 4,
    base_delay: float = 1.0,
) -> Any:
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider boundary
            if isinstance(exc, api.MonthlyIntegrityError):
                raise
            if attempt < attempts - 1 and api._is_transient(exc):
                api.threading.Event().wait(base_delay * (2**attempt))
                continue
            raise api.MonthlyIntegrityError(
                api._google_error_code(exc), f"{label} failed"
            ) from exc
    raise AssertionError("retry loop exhausted")


async def request(
    api: Any,
    adapter: Any,
    operation: str,
    payload: dict[str, Any],
    *,
    label: str,
    destructive: bool = False,
) -> Any:
    try:
        deadline = api.asyncio.get_running_loop().time() + api.GOOGLE_OPERATION_DEADLINE_SECONDS
        return await api.call_with_backoff(
            adapter,
            operation,
            payload,
            label=label,
            attempts=api.GOOGLE_API_RETRY_ATTEMPTS,
            base_delay=api.GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
            destructive=destructive,
            deadline=deadline,
        )
    except api.MonthlyIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001 - provider boundary
        raise api.MonthlyIntegrityError(
            api._google_error_code(exc), f"{label} failed"
        ) from exc
