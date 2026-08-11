"""Central config validation — fail-fast la startup pe env vars critice.

Authentik OIDC/JWKS RS256 este singurul mecanism de autentificare. Nu exista
secret JWT local de validat.

Check-uri:
- DATABASE_URL prezent, format minimal valid
- in productie, vizitele sunt citite numai din PostgreSQL, fara shadow SQLite
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from privileged_access import privileged_access_config_errors
from oidc_settings import hub_internal_secret_errors, oidc_config_errors
from rate_limit_settings import rate_limit_config_errors
from salary_identity import SALARY_PERSON_ID_HMAC_KEY_ENV, validate_salary_person_id_key
from session_auth import session_config_errors
from observability.metrics_network import metrics_network_config_errors

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISITS_DB_PATH = _REPO_ROOT / "data" / "visits" / "visits.db"
DEFAULT_VISITS_IMAGES_DIR = _REPO_ROOT / "data" / "visits" / "images"
VISITS_READ_SOURCE_ENV = "RETAIL_VISITS_READ_SOURCE"
VISITS_SHADOW_COMPARE_ENV = "RETAIL_VISITS_SHADOW_COMPARE_ENABLED"


class ConfigError(RuntimeError):
    """Ridicat la boot când env vars critice sunt invalide sau lipsă."""


RuntimeRole = Literal["web", "worker", "import"]
WorkerRole = Literal[
    "operations", "imports", "grile", "exports", "salary_exports"
]
DatabaseAuthority = Literal[
    "web", "operations", "salary_export", "sales_import", "finance_import", "migrate"
]
ARQ_CONNECTION_BUDGET_SECONDS = 3
WEB_MIN_DB_POOL_MAX_SIZE = 2
DB_PROCESS_AUTHORITY_ENV = "UNIHUB_DB_PROCESS_AUTHORITY"


@dataclass(frozen=True)
class DatabaseAuthorityContract:
    """Expected authenticated principal and its exclusive NOLOGIN authorities."""

    principal: str
    required_memberships: tuple[str, ...]
    forbidden_memberships: tuple[str, ...]
    requires_inherit: bool = True


_ALL_DATABASE_AUTHORITIES = frozenset(
    {
        "unihub_web_read",
        "unihub_business_write",
        "unihub_operations",
        "unihub_salary_export",
        "unihub_sales_import",
        "unihub_finance_import",
        "unihub_migrate",
        "unihub_schema_owner",
    }
)

DATABASE_AUTHORITY_CONTRACTS: dict[DatabaseAuthority, DatabaseAuthorityContract] = {
    "web": DatabaseAuthorityContract(
        principal="unihub_web",
        required_memberships=("unihub_web_read", "unihub_business_write"),
        forbidden_memberships=tuple(
            sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_web_read", "unihub_business_write"})
        ),
    ),
    "operations": DatabaseAuthorityContract(
        principal="unihub_operations_worker",
        required_memberships=("unihub_operations",),
        forbidden_memberships=tuple(sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_operations"})),
    ),
    "salary_export": DatabaseAuthorityContract(
        principal="unihub_salary_export_worker",
        required_memberships=("unihub_salary_export",),
        forbidden_memberships=tuple(
            sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_salary_export"})
        ),
    ),
    "sales_import": DatabaseAuthorityContract(
        principal="unihub_import_worker",
        required_memberships=("unihub_sales_import",),
        forbidden_memberships=tuple(sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_sales_import"})),
    ),
    "finance_import": DatabaseAuthorityContract(
        principal="unihub_finance_import_worker",
        required_memberships=("unihub_finance_import",),
        forbidden_memberships=tuple(
            sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_finance_import"})
        ),
    ),
    "migrate": DatabaseAuthorityContract(
        principal="unihub_migration_runner",
        required_memberships=("unihub_migrate", "unihub_schema_owner"),
        forbidden_memberships=tuple(
            sorted(_ALL_DATABASE_AUTHORITIES - {"unihub_migrate", "unihub_schema_owner"})
        ),
        requires_inherit=False,
    ),
}


def configured_database_authority() -> DatabaseAuthority | None:
    """Return the explicitly enabled authority check without inspecting a DSN."""
    value = os.getenv(DB_PROCESS_AUTHORITY_ENV, "").strip().lower()
    if not value:
        return None
    if value not in DATABASE_AUTHORITY_CONTRACTS:
        raise ConfigError(
            f"{DB_PROCESS_AUTHORITY_ENV} trebuie să fie web, operations, sales_import, "
            "finance_import, salary_export sau migrate"
        )
    return cast(DatabaseAuthority, value)


def expected_database_authority(
    role: RuntimeRole,
    worker_role: WorkerRole | None = None,
) -> DatabaseAuthority:
    if role == "worker" and worker_role == "salary_exports":
        return "salary_export"
    return cast(
        DatabaseAuthority,
        {"web": "web", "worker": "operations", "import": "sales_import"}[role],
    )


@dataclass(frozen=True)
class RuntimeConfig:
    """Configurația comună, tipizată, pentru web și worker-ele izolate."""

    role: RuntimeRole
    worker_role: WorkerRole | None
    database_authority: DatabaseAuthority | None
    db_pool_min_size: int
    db_pool_max_size: int
    db_statement_timeout_ms: int
    db_lock_timeout_ms: int
    db_idle_transaction_timeout_ms: int
    dashboard_request_deadline_ms: int | None
    campaigns_request_deadline_ms: int | None
    dashboard_global_component_concurrency: int | None
    valkey_host: str
    valkey_port: int
    valkey_database: int
    valkey_password: str | None
    valkey_url: str | None
    valkey_conn_timeout: int
    valkey_conn_retries: int
    valkey_conn_retry_delay: int
    valkey_max_connections: int
    arq_job_timeout_seconds: int
    arq_completion_wait_seconds: int
    arq_max_jobs: int
    arq_keep_result_seconds: int
    arq_failure_cooldown_seconds: int


def _parse_runtime_int(
    name: str,
    default: int,
    errors: list[str],
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{name} trebuie să fie întreg")
        return default
    if value < minimum:
        errors.append(f"{name} trebuie să fie >= {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{name} trebuie să fie <= {maximum}")
    return value


def grile_provider_stale_after_seconds() -> int:
    errors: list[str] = []
    value = _parse_runtime_int(
        "GRILE_PROVIDER_STALE_AFTER_SECONDS",
        12 * 60 * 60,
        errors,
        minimum=5 * 60,
        maximum=7 * 24 * 60 * 60,
    )
    if errors:
        raise ConfigError("; ".join(errors))
    return value


def _configured_worker_role(
    role: RuntimeRole | None,
    errors: list[str],
) -> WorkerRole | None:
    raw = os.getenv("RETAIL_WORKER_ROLE")
    configured = raw.strip().lower() if raw is not None else (
        "imports" if role == "import" else "operations"
    )
    allowed = {"operations", "imports", "grile", "exports", "salary_exports"}
    if configured not in allowed:
        errors.append(
            "RETAIL_WORKER_ROLE trebuie să fie operations, imports, grile, exports sau salary_exports"
        )
        return None
    return cast(WorkerRole, configured)


def _validated_database_authority(
    process_role: RuntimeRole,
    worker_role: WorkerRole | None,
    errors: list[str],
) -> DatabaseAuthority | None:
    try:
        authority = configured_database_authority()
    except ConfigError as exc:
        errors.append(str(exc))
        return None
    if authority is None and _is_production():
        errors.append(f"{DB_PROCESS_AUTHORITY_ENV} este obligatoriu în producție")
    elif authority is not None and authority != expected_database_authority(
        process_role, worker_role
    ):
        errors.append(
            f"{DB_PROCESS_AUTHORITY_ENV}={authority} nu corespunde procesului {process_role}"
        )
    return authority


def load_runtime_config(role: RuntimeRole | None = None) -> RuntimeConfig:
    errors: list[str] = []
    _parse_runtime_int("GRILE_PROVIDER_STALE_AFTER_SECONDS", 12 * 60 * 60, errors, minimum=5 * 60, maximum=7 * 24 * 60 * 60)
    worker_role = _configured_worker_role(role, errors)

    if role is None:
        process_role: RuntimeRole = (
            "import" if worker_role == "imports" else
            "worker" if "RETAIL_WORKER_ROLE" in os.environ else "web"
        )
    else:
        process_role = role
        if role not in {"web", "worker", "import"}:
            errors.append("role trebuie să fie web, worker sau import")
    if process_role == "import" and worker_role not in {None, "imports"}:
        errors.append("role=import necesită RETAIL_WORKER_ROLE=imports")
    if process_role == "worker" and worker_role == "imports":
        errors.append("role=worker nu poate folosi RETAIL_WORKER_ROLE=imports")

    database_authority = _validated_database_authority(
        process_role, worker_role, errors
    )

    db_pool_min_size = _parse_runtime_int("DB_POOL_MIN_SIZE", 3, errors, maximum=100)
    db_pool_max_size = _parse_runtime_int("DB_POOL_MAX_SIZE", 10, errors, maximum=100)
    db_statement_timeout_ms = _parse_runtime_int(
        "DB_STATEMENT_TIMEOUT_MS", 120000, errors, maximum=900000
    )
    db_lock_timeout_ms = _parse_runtime_int(
        "DB_LOCK_TIMEOUT_MS", 10000, errors, maximum=900000
    )
    db_idle_transaction_timeout_ms = _parse_runtime_int(
        "DB_IDLE_TRANSACTION_TIMEOUT_MS", 60000, errors, maximum=900000
    )
    if db_pool_min_size > db_pool_max_size:
        errors.append("DB_POOL_MIN_SIZE trebuie să fie <= DB_POOL_MAX_SIZE")
    if db_lock_timeout_ms >= db_statement_timeout_ms:
        errors.append("DB_LOCK_TIMEOUT_MS trebuie să fie < DB_STATEMENT_TIMEOUT_MS")
    if process_role == "web" and db_pool_max_size < WEB_MIN_DB_POOL_MAX_SIZE:
        errors.append("DB_POOL_MAX_SIZE trebuie să fie >= 2 pentru web")
    if db_idle_transaction_timeout_ms > db_statement_timeout_ms:
        errors.append(
            "DB_IDLE_TRANSACTION_TIMEOUT_MS trebuie să fie <= DB_STATEMENT_TIMEOUT_MS"
        )

    dashboard_request_deadline_ms = (
        _parse_runtime_int(
            "DASHBOARD_REQUEST_DEADLINE_MS", 2500, errors, minimum=1, maximum=3000
        )
        if process_role == "web"
        else None
    )
    campaigns_request_deadline_ms = (
        _parse_runtime_int(
            "CAMPAIGNS_REQUEST_DEADLINE_MS",
            5000,
            errors,
            minimum=100,
            maximum=10000,
        )
        if process_role == "web"
        else None
    )
    dashboard_global_component_concurrency: int | None = None
    if process_role == "web":
        dashboard_component_ceiling = db_pool_max_size - WEB_MIN_DB_POOL_MAX_SIZE
        if dashboard_component_ceiling < 1:
            errors.append(
                "DB_POOL_MAX_SIZE trebuie să fie >= 3 pentru rezerva Dashboard de 2 conexiuni"
            )
        else:
            dashboard_global_component_concurrency = _parse_runtime_int(
                "DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY",
                min(6, dashboard_component_ceiling),
                errors,
                maximum=dashboard_component_ceiling,
            )

    valkey_port = _parse_runtime_int("VALKEY_PORT", 6379, errors, maximum=65535)
    valkey_database = _parse_runtime_int("VALKEY_DATABASE", 0, errors, minimum=0, maximum=15)
    valkey_conn_timeout = _parse_runtime_int(
        "ARQ_CONN_TIMEOUT_SECONDS", 1, errors, maximum=60
    )
    valkey_conn_retries = _parse_runtime_int(
        "ARQ_CONN_RETRIES", 1, errors, minimum=0, maximum=20
    )
    valkey_conn_retry_delay = _parse_runtime_int(
        "ARQ_CONN_RETRY_DELAY_SECONDS", 1, errors, maximum=60
    )
    valkey_max_connections = _parse_runtime_int(
        "ARQ_MAX_CONNECTIONS", 4, errors, maximum=1000
    )

    arq_failure_cooldown_seconds = _parse_runtime_int(
        "ARQ_FAILURE_COOLDOWN_SECONDS", 5, errors, maximum=300
    )
    transport_budget = (
        (valkey_conn_retries + 1) * valkey_conn_timeout
        + valkey_conn_retries * valkey_conn_retry_delay
    )
    if transport_budget > ARQ_CONNECTION_BUDGET_SECONDS:
        errors.append(
            "ARQ conexiunea trebuie să respecte bugetul de 3 secunde"
        )

    # Job execution/retention belongs to worker processes. The web process
    # only needs bounded transport settings for enqueue/status operations;
    # invalid worker-only environment must not prevent web startup.
    arq_job_timeout_seconds = 1800
    arq_completion_wait_seconds = 1800 if worker_role == "imports" else 2400
    arq_max_jobs = 1
    arq_keep_result_seconds = 3600
    if process_role in {"worker", "import"}:
        arq_job_timeout_seconds = _parse_runtime_int(
            "ARQ_JOB_TIMEOUT_SECONDS", 1800, errors, maximum=7200
        )
        arq_completion_wait_seconds = _parse_runtime_int(
            "ARQ_JOB_COMPLETION_WAIT_SECONDS",
            arq_completion_wait_seconds,
            errors,
            maximum=7200,
        )
        arq_max_jobs = _parse_runtime_int("ARQ_MAX_JOBS", 1, errors, maximum=32)
        arq_keep_result_seconds = _parse_runtime_int(
            "ARQ_KEEP_RESULT_SECONDS", 3600, errors, maximum=86400
        )
        if arq_completion_wait_seconds < arq_job_timeout_seconds:
            errors.append(
                "ARQ_JOB_COMPLETION_WAIT_SECONDS trebuie să fie >= ARQ_JOB_TIMEOUT_SECONDS"
            )
        if arq_keep_result_seconds < max(
            arq_job_timeout_seconds, arq_completion_wait_seconds
        ):
            errors.append(
                "ARQ_KEEP_RESULT_SECONDS trebuie să fie >= cel mai lung job ARQ"
            )
        if valkey_max_connections < arq_max_jobs:
            errors.append("ARQ_MAX_CONNECTIONS trebuie să fie >= ARQ_MAX_JOBS")

    if errors:
        raise ConfigError(
            "Runtime config invalid la startup:\n  - " + "\n  - ".join(errors)
        )

    return RuntimeConfig(
        role=process_role,
        worker_role=worker_role,
        database_authority=database_authority,
        db_pool_min_size=db_pool_min_size,
        db_pool_max_size=db_pool_max_size,
        db_statement_timeout_ms=db_statement_timeout_ms,
        db_lock_timeout_ms=db_lock_timeout_ms,
        db_idle_transaction_timeout_ms=db_idle_transaction_timeout_ms,
        dashboard_request_deadline_ms=dashboard_request_deadline_ms,
        campaigns_request_deadline_ms=campaigns_request_deadline_ms,
        dashboard_global_component_concurrency=dashboard_global_component_concurrency,
        valkey_host=os.getenv("VALKEY_HOST", "127.0.0.1").strip() or "127.0.0.1",
        valkey_port=valkey_port,
        valkey_database=valkey_database,
        valkey_password=os.getenv("VALKEY_PASSWORD") or None,
        valkey_url=os.getenv("VALKEY_URL", "").strip() or None,
        valkey_conn_timeout=valkey_conn_timeout,
        valkey_conn_retries=valkey_conn_retries,
        valkey_conn_retry_delay=valkey_conn_retry_delay,
        valkey_max_connections=valkey_max_connections,
        arq_job_timeout_seconds=arq_job_timeout_seconds,
        arq_completion_wait_seconds=arq_completion_wait_seconds,
        arq_max_jobs=arq_max_jobs,
        arq_keep_result_seconds=arq_keep_result_seconds,
        arq_failure_cooldown_seconds=arq_failure_cooldown_seconds,
    )


def validate_runtime_config(role: RuntimeRole | None = None) -> RuntimeConfig:
    """Alias explicit pentru boot checks în fiecare proces."""
    return load_runtime_config(role)


def _is_production() -> bool:
    return os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"


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
