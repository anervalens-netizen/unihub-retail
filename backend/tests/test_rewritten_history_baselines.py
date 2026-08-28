from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASELINE = bytes(
    (
        0x9C,
        0xBE,
        0x26,
        0xB5,
        0x88,
        0xD6,
        0x90,
        0x1A,
        0x5A,
        0x31,
        0x2B,
        0x62,
        0x62,
        0x77,
        0x5F,
        0x30,
        0x93,
        0xC5,
        0x4F,
        0xDC,
    )
).hex()
EXPECTED_TREE = bytes(
    (
        0x20,
        0xA1,
        0x70,
        0x6C,
        0xF8,
        0x54,
        0xF5,
        0x04,
        0x23,
        0x65,
        0x26,
        0x81,
        0x4A,
        0x3E,
        0xE7,
        0xD2,
        0x77,
        0x57,
        0x95,
        0x98,
    )
).hex()
RELEASE_A_GATE = ROOT / "scripts" / "run_release_a_schema_gate.sh"
FRONTEND_MANIFEST = ROOT / "scripts" / "frontend-critical-coverage.json"
MIGRATION_068 = "backend/db/migrations/068_grile_v2_forecast_digest_authority.sql"
MIGRATION_069 = "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _release_a_baseline() -> str:
    text = RELEASE_A_GATE.read_text(encoding="utf-8")
    match = re.search(r'^BASELINE_SHA="([0-9a-f]{40})"$', text, re.MULTILINE)
    assert match is not None, "Release-A operational BASELINE_SHA is missing or malformed"
    return match.group(1)


def _frontend_baseline() -> str:
    manifest = json.loads(FRONTEND_MANIFEST.read_text(encoding="utf-8"))
    baseline = manifest.get("baseline_source_sha")
    assert isinstance(baseline, str) and re.fullmatch(r"[0-9a-f]{40}", baseline), (
        "frontend operational baseline_source_sha is missing or malformed"
    )
    return baseline


def test_release_a_operational_baseline_parses() -> None:
    assert _release_a_baseline()


def test_frontend_operational_baseline_parses() -> None:
    assert _frontend_baseline()


def test_operational_baselines_match() -> None:
    assert _release_a_baseline() == _frontend_baseline()


def test_operational_baseline_matches_rewritten_identity() -> None:
    assert _release_a_baseline() == EXPECTED_BASELINE


def test_operational_baseline_commit_resolves() -> None:
    result = _git("cat-file", "-e", f"{EXPECTED_BASELINE}^{{commit}}")
    assert result.returncode == 0, result.stderr


def test_operational_baseline_tree_matches_semantic_snapshot() -> None:
    result = _git("rev-parse", f"{EXPECTED_BASELINE}^{{tree}}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == EXPECTED_TREE


def test_operational_baseline_contains_migration_068() -> None:
    result = _git("cat-file", "-e", f"{EXPECTED_BASELINE}:{MIGRATION_068}")
    assert result.returncode == 0, result.stderr


def test_operational_baseline_excludes_migration_069() -> None:
    result = _git("cat-file", "-e", f"{EXPECTED_BASELINE}:{MIGRATION_069}")
    assert result.returncode != 0, "operational baseline must remain pre-069"


def test_frontend_operational_baseline_supports_changed_line_diff() -> None:
    result = _git(
        "diff",
        "--unified=0",
        "--diff-filter=AM",
        EXPECTED_BASELINE,
        "--",
        "src",
    )
    assert result.returncode == 0, result.stderr
