#!/usr/bin/env python3
"""Stage/review P&L TVA candidates without any live P&L apply route."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.estimate_store_pnl import month_date
from services.store_pnl_shadow import (
    ShadowGenerationError,
    capture_shadow,
    promote_shadow_generation,
    rollback_shadow_pointer,
    stage_shadow_capture,
)


REPO_DIR = BACKEND_DIR.parent


def parse_scope(value: str) -> tuple[str, date]:
    try:
        company, month = value.rsplit(":", 1)
        return company.strip(), month_date(month)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Scope-ul trebuie sa fie Company:YYYY-MM.") from exc


async def run(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ShadowGenerationError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        if args.promote_shadow:
            if args.expected_revision is None:
                raise ShadowGenerationError("--expected-revision este obligatoriu pentru CAS promote.")
            revision = await promote_shadow_generation(
                connection,
                args.promote_shadow,
                expected_revision=args.expected_revision,
            )
            print(json.dumps({"shadow_pointer_revision": revision, "effective_apply": "BLOCKED"}))
            return 0
        if args.rollback_shadow:
            if args.expected_revision is None:
                raise ShadowGenerationError("--expected-revision este obligatoriu pentru CAS rollback.")
            revision = await rollback_shadow_pointer(
                connection,
                expected_revision=args.expected_revision,
            )
            print(json.dumps({"shadow_pointer_revision": revision, "effective_apply": "BLOCKED"}))
            return 0
        if args.input_cutoff is None or not args.scope:
            raise ShadowGenerationError("--input-cutoff si cel putin un --scope sunt obligatorii pentru shadow capture.")
        capture = await capture_shadow(
            connection,
            args.scope,
            args.input_cutoff,
            baseline_generation_id=args.baseline_generation,
        )
        report = capture.report()
        if args.stage_shadow:
            report["generation_id"] = str(await stage_shadow_capture(connection, capture))
            report["staged"] = True
        else:
            report["staged"] = False
        print(json.dumps(report, sort_keys=True))
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare legacy-v2 cu effective-v3 pe acelasi snapshot; apply P&L este blocat.",
    )
    parser.add_argument("--input-cutoff", type=month_date, help="Cutoff fix YYYY-MM pentru capture.")
    parser.add_argument("--scope", action="append", type=parse_scope, help="Repeat: Company:YYYY-MM.")
    parser.add_argument("--baseline-generation", type=UUID, help="Legacy-v2 prior cu acelasi scope pentru drift.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--stage-shadow", action="store_true", help="Persistă numai generația/pre-image shadow.")
    actions.add_argument("--promote-shadow", type=UUID, help="CAS: schimbă numai pointerul de review shadow.")
    actions.add_argument("--rollback-shadow", action="store_true", help="CAS: revine pointerul shadow la generația precedentă.")
    parser.add_argument("--expected-revision", type=int, help="Revision obligatorie pentru operații CAS.")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ShadowGenerationError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
