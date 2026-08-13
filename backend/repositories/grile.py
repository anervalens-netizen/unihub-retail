from __future__ import annotations

import asyncpg

from repositories.grile_persistence import (
    GRILE_RUN_LEASE_EXPIRED,
    GRILE_RUN_QUEUED_LEASE_SECONDS,
    GRILE_RUN_RUNNING_LEASE_SECONDS,
    GRILE_STORE_REFRESH_LEASE_EXPIRED,
    GRILE_STORE_REFRESH_QUEUED_LEASE_SECONDS,
    GRILE_STORE_REFRESH_RUNNING_LEASE_SECONDS,
    _apply_error_projection,
    _apply_success_projection,
    _record_observation,
    _reconcile_stale_runs_on_connection,
    _reconcile_stale_store_refreshes_on_connection,
    _status_params,
)
from repositories.grile_reads import GrileReadQueries
from repositories.grile_runs import GrileRunQueries
from repositories.grile_store_refreshes import GrileStoreRefreshQueries


class GrileRepository(GrileRunQueries, GrileStoreRefreshQueries, GrileReadQueries):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
