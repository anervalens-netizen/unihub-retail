"""Central config validation — fail-fast la startup pe env vars critice.

Authentik OIDC/JWKS RS256 este singurul mecanism de autentificare. Nu exista
secret JWT local de validat.

Check-uri:
- DATABASE_URL prezent, format minimal valid
- in productie, vizitele sunt citite numai din PostgreSQL, fara shadow SQLite
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from privileged_access import privileged_access_config_errors
from oidc_settings import hub_internal_secret_errors, oidc_config_errors
from rate_limit_settings import rate_limit_config_errors
from salary_identity import SALARY_PERSON_ID_HMAC_KEY_ENV, validate_salary_person_id_key
from session_auth import session_config_errors
from observability.metrics_network import metrics_network_config_errors
from runtime_config import (
    ARQ_CONNECTION_BUDGET_SECONDS as ARQ_CONNECTION_BUDGET_SECONDS,
    DATABASE_AUTHORITY_CONTRACTS as DATABASE_AUTHORITY_CONTRACTS,
    DB_PROCESS_AUTHORITY_ENV as DB_PROCESS_AUTHORITY_ENV,
    WEB_MIN_DB_POOL_MAX_SIZE as WEB_MIN_DB_POOL_MAX_SIZE,
    ConfigError as ConfigError,
    DatabaseAuthority as DatabaseAuthority,
    DatabaseAuthorityContract as DatabaseAuthorityContract,
    RuntimeConfig as RuntimeConfig,
    RuntimeRole as RuntimeRole,
    WorkerRole as WorkerRole,
    _configured_worker_role as _configured_worker_role,
    _is_production as _is_production,
    _parse_runtime_int as _parse_runtime_int,
    _validated_database_authority as _validated_database_authority,
    configured_database_authority as configured_database_authority,
    expected_database_authority as expected_database_authority,
    grile_provider_stale_after_seconds as grile_provider_stale_after_seconds,
    load_runtime_config as load_runtime_config,
    validate_runtime_config as validate_runtime_config,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISITS_DB_PATH = _REPO_ROOT / "data" / "visits" / "visits.db"
DEFAULT_VISITS_IMAGES_DIR = _REPO_ROOT / "data" / "visits" / "images"
VISITS_READ_SOURCE_ENV = "RETAIL_VISITS_READ_SOURCE"
VISITS_SHADOW_COMPARE_ENV = "RETAIL_VISITS_SHADOW_COMPARE_ENABLED"



_DEFAULT_DEVELOPMENT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
_MAX_CORS_ORIGINS = 16


def _normalized_cors_origin(value: str, *, production: bool) -> str:
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("contains whitespace or control characters")
    if "*" in value:
        raise ValueError("wildcards are forbidden")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("has an invalid port") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("must use http or https")
    if production and parsed.scheme != "https":
        raise ValueError("must use https in production")
    if not parsed.hostname:
        raise ValueError("must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("must not contain credentials")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("must be an origin without path, query, or fragment")

    hostname = parsed.hostname.casefold()
    if production and hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("must not target loopback in production")
    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme == "https" else 80
    authority = host if port in {None, default_port} else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def cors_config_errors(production: bool | None = None) -> list[str]:
    production = _is_production() if production is None else production
    raw = os.getenv("CORS_ORIGINS")
    if raw is None or not raw.strip():
        if production:
            return ["CORS_ORIGINS is required in production"]
        values = list(_DEFAULT_DEVELOPMENT_CORS_ORIGINS)
    else:
        values = raw.split(",")

    errors: list[str] = []
    if len(values) > _MAX_CORS_ORIGINS:
        errors.append(f"CORS_ORIGINS supports at most {_MAX_CORS_ORIGINS} origins")
    seen: set[str] = set()
    for index, item in enumerate(values[: _MAX_CORS_ORIGINS], start=1):
        if not item:
            errors.append(f"CORS_ORIGINS entry {index} is empty")
            continue
        try:
            origin = _normalized_cors_origin(item, production=production)
        except ValueError as exc:
            errors.append(f"CORS_ORIGINS entry {index} {exc}")
            continue
        if origin in seen:
            errors.append(f"CORS_ORIGINS contains duplicate origin {origin}")
        seen.add(origin)
    return errors


def get_cors_origins(production: bool | None = None) -> tuple[str, ...]:
    production = _is_production() if production is None else production
    errors = cors_config_errors(production)
    if errors:
        raise ConfigError("CORS config invalid:\n  - " + "\n  - ".join(errors))
    raw = os.getenv("CORS_ORIGINS")
    values = (
        raw.split(",")
        if raw is not None and raw.strip()
        else list(_DEFAULT_DEVELOPMENT_CORS_ORIGINS)
    )
    return tuple(
        _normalized_cors_origin(value, production=production) for value in values
    )


def get_visits_db_path() -> Path:
    return Path(os.getenv("VISITS_DB_PATH", str(DEFAULT_VISITS_DB_PATH))).expanduser()


def get_visits_images_dir() -> Path:
    return Path(os.getenv("VISITS_IMAGES_DIR", str(DEFAULT_VISITS_IMAGES_DIR))).expanduser()


def get_visits_read_source() -> str:
    value = os.getenv(VISITS_READ_SOURCE_ENV, "postgres").strip().lower()
    return value if value in {"sqlite", "postgres"} else "postgres"


def visits_shadow_compare_enabled() -> bool:
    return os.getenv(VISITS_SHADOW_COMPARE_ENV, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def validate_required_env_vars(role: RuntimeRole | None = None) -> RuntimeConfig:
    """Validează env vars critice. Ridică ConfigError dacă ceva e greșit.

    Se apelează cât mai devreme în lifespan — înainte de init_db_pool,
    înainte de bootstrap. Dacă rupem ceva aici, backend-ul refuză să pornească
    și systemd loghează eroarea clar.
    """
    errors: list[str] = []
    runtime_config: RuntimeConfig | None = None
    try:
        runtime_config = load_runtime_config(role)
    except ConfigError as exc:
        errors.extend(str(exc).splitlines())

    # DATABASE_URL
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        errors.append("DATABASE_URL este gol sau nesetat")
    elif not db_url.startswith(("postgresql://", "postgres://")):
        errors.append(
            f"DATABASE_URL are schemă invalidă (găsit: {db_url[:20]}...); "
            "trebuie să înceapă cu postgresql:// sau postgres://"
        )

    read_source_raw = os.getenv(VISITS_READ_SOURCE_ENV, "postgres").strip().lower()
    if read_source_raw not in {"sqlite", "postgres"}:
        errors.append(
            f"{VISITS_READ_SOURCE_ENV} trebuie sa fie sqlite sau postgres"
        )
    if _is_production():
        if read_source_raw != "postgres":
            errors.append(
                f"{VISITS_READ_SOURCE_ENV} trebuie sa fie postgres dupa cutover"
            )
        if visits_shadow_compare_enabled():
            errors.append(
                f"{VISITS_SHADOW_COMPARE_ENV} trebuie sa fie false dupa cutover"
            )

    errors.extend(privileged_access_config_errors(_is_production()))
    errors.extend(oidc_config_errors(_is_production()))
    errors.extend(hub_internal_secret_errors())
    errors.extend(rate_limit_config_errors(_is_production()))
    errors.extend(session_config_errors(_is_production()))
    errors.extend(metrics_network_config_errors(required=_is_production()))
    errors.extend(cors_config_errors(_is_production()))

    person_id_key = os.getenv(SALARY_PERSON_ID_HMAC_KEY_ENV)
    if _is_production():
        if person_id_key is None or person_id_key == "":
            errors.append(f"{SALARY_PERSON_ID_HMAC_KEY_ENV} is required in production")
        else:
            try:
                validate_salary_person_id_key(person_id_key)
            except ValueError as exc:
                errors.append(str(exc))
    elif person_id_key not in (None, ""):
        try:
            validate_salary_person_id_key(person_id_key)
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ConfigError(
            "Config invalid la startup:\n  - " + "\n  - ".join(errors)
        )
    if runtime_config is None:
        raise ConfigError("Runtime config nu a fost încărcat")
    return runtime_config
