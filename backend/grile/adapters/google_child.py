from __future__ import annotations

import json
import sys
from typing import Any

from grile.adapters.retry import retry_google_call
from services.grile_sheets import build_services, close_services, fetch_grila, fetch_mod_time



def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: google_child <sheet_id> <template_version>", file=sys.stderr)
        return 64
    sheet_id, template_version = argv[1:]
    if not sheet_id or len(sheet_id) > 256 or template_version not in {"v2", "v3"}:
        print("invalid child arguments", file=sys.stderr)
        return 64

    sheets_service = drive_service = None
    try:
        sheets_service, drive_service = build_services()
        value_ranges = retry_google_call(
            lambda: fetch_grila(sheets_service, sheet_id, template_version),
            attempts=4,
            base_delay=1.0,
        )
        modified_time = retry_google_call(
            lambda: fetch_mod_time(drive_service, sheet_id),
            attempts=4,
            base_delay=1.0,
        )
        payload = {
            "value_ranges": value_ranges,
            "modified_time": modified_time,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - isolated provider boundary
        message = f"{type(exc).__name__}: {exc}"[:1000]
        print(message, file=sys.stderr)
        return 1
    finally:
        close_services(sheets_service, drive_service)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
