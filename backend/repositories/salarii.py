from __future__ import annotations

import asyncpg

from repositories.salarii_detail import SalariiDetailQueries
from repositories.salarii_scope import MIN_SALARY_FOR_AVERAGE, _salary_scope
from repositories.salarii_summary import SalariiSummaryQueries


class SalariiRepository(SalariiSummaryQueries, SalariiDetailQueries):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
