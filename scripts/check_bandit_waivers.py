#!/usr/bin/env python3
"""Require every Bandit baseline suppression to have an owned, expiring waiver."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    baseline = json.loads((ROOT / ".bandit-baseline.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / ".bandit-waivers.json").read_text(encoding="utf-8"))
    if policy.get("version") != 1:
        raise SystemExit("Unsupported Bandit waiver policy version")

    expected: set[tuple[str, str, int]] = set()
    for waiver in policy.get("waivers", []):
        filename = waiver.get("filename")
        test_id = waiver.get("test_id")
        lines = waiver.get("lines")
        if not isinstance(filename, str) or not isinstance(test_id, str):
            raise SystemExit("Bandit waiver filename/test_id must be strings")
        if not isinstance(lines, list) or not lines or not all(isinstance(line, int) for line in lines):
            raise SystemExit(f"Bandit waiver {filename}:{test_id} requires integer lines")
        if not str(waiver.get("owner", "")).strip() or len(str(waiver.get("rationale", "")).strip()) < 20:
            raise SystemExit(f"Bandit waiver {filename}:{test_id} lacks owner/rationale")
        try:
            expires = date.fromisoformat(str(waiver["expires"]))
        except (KeyError, ValueError) as exc:
            raise SystemExit(f"Bandit waiver {filename}:{test_id} has invalid expiry") from exc
        if expires < date.today():
            raise SystemExit(f"Bandit waiver expired: {filename}:{test_id} on {expires}")
        for line in lines:
            key = (filename, test_id, line)
            if key in expected:
                raise SystemExit(f"Duplicate Bandit waiver: {key}")
            expected.add(key)

    observed = {
        (str(item["filename"]), str(item["test_id"]), int(item["line_number"]))
        for item in baseline.get("results", [])
    }
    missing = sorted(observed - expected)
    stale = sorted(expected - observed)
    if missing or stale:
        raise SystemExit(f"Bandit waiver drift: missing={missing}, stale={stale}")
    print(f"Bandit waivers valid: {len(observed)} findings")


if __name__ == "__main__":
    main()
