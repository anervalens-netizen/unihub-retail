#!/usr/bin/env python3
"""Safely materialize an active legacy Promo v1 generation before runtime v2.

Default is a complete read-only dry-run.  ``--apply`` creates one immutable
v2 generation and switches ``current.json`` exactly once with pointer CAS.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.product_lists import get_data_dir  # noqa: E402
from services.promo_generation_migration import (  # noqa: E402
    PromoGenerationMigrationError,
    migrate_legacy_promo_generation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="promovează atomic generația v2 validată")
    parser.add_argument("--data-dir", type=Path, default=None, help="directorul data (implicit UNIHUB_DATA_DIR/data)")
    args = parser.parse_args()
    try:
        result = migrate_legacy_promo_generation(
            data_dir=(args.data_dir or get_data_dir()),
            apply=args.apply,
        )
    except PromoGenerationMigrationError as exc:
        print(f"promo-v1-v2: failed: {exc}", file=sys.stderr)
        return 2
    print(
        "promo-v1-v2:"
        f" status={result.status}"
        f" previous={result.previous_generation_id}"
        f" generation={result.generation_id or '-'}"
        f" sources={result.source_count}"
        f" promotions={result.promotion_count}"
        f" pointer_sha256={result.pointer_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
