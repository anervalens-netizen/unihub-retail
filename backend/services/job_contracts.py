from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arq.jobs import Job
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError


class JobQueueUnavailableError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            detail="Job backend unavailable",
        )


class JobPublishUncertainError(HTTPException):
    def __init__(
        self,
        *,
        job_id: str | None = None,
        operation_id: int | None = None,
    ) -> None:
        self.job_id = job_id
        self.operation_id = operation_id
        super().__init__(status_code=503, detail=self._detail())

    def _detail(self) -> dict[str, object | None]:
        return {
            "status": "unknown",
            "job_id": self.job_id,
            "operation_id": self.operation_id,
        }

    def attach_operation_id(self, operation_id: int) -> None:
        self.operation_id = operation_id
        object.__setattr__(self, "detail", self._detail())


ARQ_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)


class JobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    NOT_FOUND = "not_found"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNKNOWN = "unknown"


@dataclass
class JobResult:
    job_id: str
    status: JobStatus
    result: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class GrileEnqueueResult:
    status: str
    run_id: int
    job: Job | None = None
    run: dict | None = None


@dataclass
class GrileStoreRefreshEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    operation: dict | None = None


@dataclass
class GrileMonthlyEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    job_id: str | None = None
    operation: dict | None = None


@dataclass
class GrileTargetSyncEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    operation: dict | None = None


SALES_IMPORT_QUEUE_NAME = "arq:retail:imports"
OPERATIONS_QUEUE_NAME = "arq:retail:operations"
GRILE_QUEUE_NAME = "arq:retail:grile"
EXPORT_QUEUE_NAME = "arq:retail:exports"
SALARY_EXPORT_QUEUE_NAME = "arq:retail:salary-exports"
MONTHLY_QUEUE_PUBLISH_FAILED = "monthly_queue_publish_failed"

