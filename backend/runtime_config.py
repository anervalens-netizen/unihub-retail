"""Typed runtime-process configuration and bounded environment parsing."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

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


def _process_roles(
    role: RuntimeRole | None,
    errors: list[str],
) -> tuple[RuntimeRole, WorkerRole | None]:
    _parse_runtime_int(
        "GRILE_PROVIDER_STALE_AFTER_SECONDS", 12 * 60 * 60, errors,
        minimum=5 * 60, maximum=7 * 24 * 60 * 60,
    )
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
    return process_role, worker_role


def _database_settings(
    process_role: RuntimeRole,
    errors: list[str],
) -> tuple[int, int, int, int, int]:
    pool_min = _parse_runtime_int("DB_POOL_MIN_SIZE", 3, errors, maximum=100)
    pool_max = _parse_runtime_int("DB_POOL_MAX_SIZE", 10, errors, maximum=100)
    statement = _parse_runtime_int(
        "DB_STATEMENT_TIMEOUT_MS", 120000, errors, maximum=900000
    )
    lock = _parse_runtime_int("DB_LOCK_TIMEOUT_MS", 10000, errors, maximum=900000)
    idle = _parse_runtime_int(
        "DB_IDLE_TRANSACTION_TIMEOUT_MS", 60000, errors, maximum=900000
    )
    if pool_min > pool_max:
        errors.append("DB_POOL_MIN_SIZE trebuie să fie <= DB_POOL_MAX_SIZE")
    if lock >= statement:
        errors.append("DB_LOCK_TIMEOUT_MS trebuie să fie < DB_STATEMENT_TIMEOUT_MS")
    if process_role == "web" and pool_max < WEB_MIN_DB_POOL_MAX_SIZE:
        errors.append("DB_POOL_MAX_SIZE trebuie să fie >= 2 pentru web")
    if idle > statement:
        errors.append(
            "DB_IDLE_TRANSACTION_TIMEOUT_MS trebuie să fie <= DB_STATEMENT_TIMEOUT_MS"
        )
    return pool_min, pool_max, statement, lock, idle


def _dashboard_settings(
    process_role: RuntimeRole,
    db_pool_max_size: int,
    errors: list[str],
) -> tuple[int | None, int | None, int | None]:
    if process_role != "web":
        return None, None, None
    deadline = _parse_runtime_int(
        "DASHBOARD_REQUEST_DEADLINE_MS", 2500, errors, minimum=1, maximum=3000
    )
    campaigns_deadline = _parse_runtime_int(
        "CAMPAIGNS_REQUEST_DEADLINE_MS", 5000, errors, minimum=100, maximum=10000
    )
    ceiling = db_pool_max_size - WEB_MIN_DB_POOL_MAX_SIZE
    concurrency: int | None = None
    if ceiling < 1:
        errors.append(
            "DB_POOL_MAX_SIZE trebuie să fie >= 3 pentru rezerva Dashboard de 2 conexiuni"
        )
    else:
        concurrency = _parse_runtime_int(
            "DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY", min(6, ceiling), errors,
            maximum=ceiling,
        )
    return deadline, campaigns_deadline, concurrency


def _valkey_settings(errors: list[str]) -> tuple[int, int, int, int, int]:
    port = _parse_runtime_int("VALKEY_PORT", 6379, errors, maximum=65535)
    database = _parse_runtime_int(
        "VALKEY_DATABASE", 0, errors, minimum=0, maximum=15
    )
    timeout = _parse_runtime_int("ARQ_CONN_TIMEOUT_SECONDS", 1, errors, maximum=60)
    retries = _parse_runtime_int(
        "ARQ_CONN_RETRIES", 1, errors, minimum=0, maximum=20
    )
    retry_delay = _parse_runtime_int(
        "ARQ_CONN_RETRY_DELAY_SECONDS", 1, errors, maximum=60
    )
    return port, database, timeout, retries, retry_delay


def _arq_settings(
    process_role: RuntimeRole,
    worker_role: WorkerRole | None,
    *,
    timeout: int,
    retries: int,
    retry_delay: int,
    max_connections: int,
    errors: list[str],
) -> tuple[int, int, int, int, int]:
    failure_cooldown = _parse_runtime_int(
        "ARQ_FAILURE_COOLDOWN_SECONDS", 5, errors, maximum=300
    )
    transport_budget = (retries + 1) * timeout + retries * retry_delay
    if transport_budget > ARQ_CONNECTION_BUDGET_SECONDS:
        errors.append("ARQ conexiunea trebuie să respecte bugetul de 3 secunde")
    job_timeout = 1800
    completion_wait = 1800 if worker_role == "imports" else 2400
    max_jobs = 1
    keep_result = 3600
    if process_role in {"worker", "import"}:
        job_timeout = _parse_runtime_int(
            "ARQ_JOB_TIMEOUT_SECONDS", 1800, errors, maximum=7200
        )
        completion_wait = _parse_runtime_int(
            "ARQ_JOB_COMPLETION_WAIT_SECONDS", completion_wait, errors, maximum=7200
        )
        max_jobs = _parse_runtime_int("ARQ_MAX_JOBS", 1, errors, maximum=32)
        keep_result = _parse_runtime_int(
            "ARQ_KEEP_RESULT_SECONDS", 3600, errors, maximum=86400
        )
        if completion_wait < job_timeout:
            errors.append(
                "ARQ_JOB_COMPLETION_WAIT_SECONDS trebuie să fie >= ARQ_JOB_TIMEOUT_SECONDS"
            )
        if keep_result < max(job_timeout, completion_wait):
            errors.append(
                "ARQ_KEEP_RESULT_SECONDS trebuie să fie >= cel mai lung job ARQ"
            )
        if max_connections < max_jobs:
            errors.append("ARQ_MAX_CONNECTIONS trebuie să fie >= ARQ_MAX_JOBS")
    return job_timeout, completion_wait, max_jobs, keep_result, failure_cooldown


def load_runtime_config(role: RuntimeRole | None = None) -> RuntimeConfig:
    errors: list[str] = []
    process_role, worker_role = _process_roles(role, errors)
    database_authority = _validated_database_authority(
        process_role, worker_role, errors
    )
    db_settings = _database_settings(process_role, errors)
    pool_min, pool_max, statement_timeout, lock_timeout, idle_timeout = db_settings
    dashboard_deadline, campaigns_deadline, dashboard_concurrency = (
        _dashboard_settings(process_role, pool_max, errors)
    )
    valkey_port, valkey_database, conn_timeout, conn_retries, retry_delay = (
        _valkey_settings(errors)
    )
    max_connections = _parse_runtime_int(
        "ARQ_MAX_CONNECTIONS", 4, errors, maximum=1000
    )
    job_timeout, completion_wait, max_jobs, keep_result, failure_cooldown = (
        _arq_settings(
            process_role,
            worker_role,
            timeout=conn_timeout,
            retries=conn_retries,
            retry_delay=retry_delay,
            max_connections=max_connections,
            errors=errors,
        )
    )
    if errors:
        raise ConfigError(
            "Runtime config invalid la startup:\n  - " + "\n  - ".join(errors)
        )
    return RuntimeConfig(
        role=process_role,
        worker_role=worker_role,
        database_authority=database_authority,
        db_pool_min_size=pool_min,
        db_pool_max_size=pool_max,
        db_statement_timeout_ms=statement_timeout,
        db_lock_timeout_ms=lock_timeout,
        db_idle_transaction_timeout_ms=idle_timeout,
        dashboard_request_deadline_ms=dashboard_deadline,
        campaigns_request_deadline_ms=campaigns_deadline,
        dashboard_global_component_concurrency=dashboard_concurrency,
        valkey_host=os.getenv("VALKEY_HOST", "127.0.0.1").strip() or "127.0.0.1",
        valkey_port=valkey_port,
        valkey_database=valkey_database,
        valkey_password=os.getenv("VALKEY_PASSWORD") or None,
        valkey_url=os.getenv("VALKEY_URL", "").strip() or None,
        valkey_conn_timeout=conn_timeout,
        valkey_conn_retries=conn_retries,
        valkey_conn_retry_delay=retry_delay,
        valkey_max_connections=max_connections,
        arq_job_timeout_seconds=job_timeout,
        arq_completion_wait_seconds=completion_wait,
        arq_max_jobs=max_jobs,
        arq_keep_result_seconds=keep_result,
        arq_failure_cooldown_seconds=failure_cooldown,
    )


def validate_runtime_config(role: RuntimeRole | None = None) -> RuntimeConfig:
    """Alias explicit pentru boot checks în fiecare proces."""
    return load_runtime_config(role)


def _is_production() -> bool:
    return os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"
