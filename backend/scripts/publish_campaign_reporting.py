#!/usr/bin/env python3
"""Controlled backfill/publish for the immutable Insight Campaigns contract.

Default mode is read-only.  ``--apply`` is deliberately explicit and requires
the dedicated imports-worker DSN, which has only the narrow publisher function
plus read access required to build the candidate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
load_dotenv(REPO_DIR / ".env.worker")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.connection import verify_database_connection_authority
from services.campaign_reporting import CampaignReportingPublisher
from services.contest_reporting import ContestReportingPublisher


MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _month(value: str) -> str:
    if not MONTH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("Luna trebuie sa fie YYYY-MM.")
    return value


async def _periods(connection: asyncpg.Connection, requested: list[str], all_months: bool) -> list[str]:
    if requested:
        return sorted(set(requested))
    if not all_months:
        raise RuntimeError("Indica --month YYYY-MM (repetabil) sau --all.")
    rows = await connection.fetch(
        """
        SELECT DISTINCT import_month
        FROM import_snapshots
        WHERE status = 'completed'
        ORDER BY import_month
        """
    )
    return [str(row["import_month"]) for row in rows]


async def _dry_run(connection: asyncpg.Connection, periods: list[str]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for period in periods:
        row = await connection.fetchrow(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM import_snapshots
                    WHERE import_month = $1 AND status = 'completed'
                ) AS sales_snapshot_available,
                (
                    SELECT revision FROM campaign_reporting_heads
                    WHERE period = $1
                ) AS current_revision,
                (
                    SELECT COUNT(*)::BIGINT
                    FROM reporting_agent_month
                    WHERE import_month = $1
                      AND locatie NOT ILIKE 'TR%'
                      AND locatie NOT ILIKE '%cartel%'
                ) AS eligible_store_agents
            """,
            period,
        )
        out.append({
            "period": period,
            "mode": "dry_run",
            "sales_snapshot_available": bool(row["sales_snapshot_available"]),
            "current_revision": row["current_revision"],
            "eligible_store_agents": int(row["eligible_store_agents"] or 0),
            "will_write": False,
        })
    return out


async def run(args: argparse.Namespace) -> int:
    if args.apply:
        database_url = os.getenv("CAMPAIGN_REPORTING_DATABASE_URL", "")
        if not database_url:
            raise RuntimeError(
                "--apply cere CAMPAIGN_REPORTING_DATABASE_URL al imports workerului."
            )
    else:
        database_url = (
            os.getenv("CAMPAIGN_REPORTING_DATABASE_URL", "")
            or os.getenv("DATABASE_URL", "")
        )
    if not database_url:
        raise RuntimeError("Lipsește un DATABASE_URL pentru verificarea read-only.")

    connection = await asyncpg.connect(database_url)
    try:
        periods = await _periods(connection, args.month, args.all)
        if not args.apply:
            print(json.dumps(await _dry_run(connection, periods), sort_keys=True))
            return 0
        await verify_database_connection_authority(connection, "sales_import")
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=4,
        command_timeout=1800,
        server_settings={"application_name": "unihub-retail-campaign-reporting-backfill"},
    )
    try:
        publisher = CampaignReportingPublisher(pool)
        contest_publisher = ContestReportingPublisher(pool)
        results = []
        for period in periods:
            result = await publisher.publish_month(
                period,
                requested_by_sub=args.requested_by,
                reason=args.reason,
            )
            contest_result = await contest_publisher.publish_month(
                period,
                requested_by_sub=args.requested_by,
                reason=args.reason,
            )
            results.append({"campaign": result.__dict__, "contest": contest_result.__dict__})
        print(json.dumps(results, sort_keys=True))
    finally:
        await pool.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill controlat pentru read-modelurile Campaigns v3 și Concursuri v1; default read-only."
    )
    parser.add_argument("--month", action="append", type=_month, default=[])
    parser.add_argument("--all", action="store_true", help="Selectează toate lunile sales complete.")
    parser.add_argument("--apply", action="store_true", help="Scrie generații immutable prin CAS.")
    parser.add_argument("--requested-by", default="operator:campaign-reporting-backfill")
    parser.add_argument("--reason", default="controlled_campaign_reporting_backfill")
    args = parser.parse_args()
    if args.all and args.month:
        parser.error("--all și --month nu se combină.")
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
