from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts/render_production_release_notes.py"
SPEC = importlib.util.spec_from_file_location("render_production_release_notes", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_notes)

SOURCE_SHA = "a" * 40
OLD_SHA = "b" * 40
ARTIFACT_SHA = "c" * 64
SBOM_SHA = "d" * 64


def valid_values() -> dict[str, str]:
    return {
        "PROMOTION_SCHEMA_VERSION": "1",
        "RELEASE_ID": f"retail-release-{SOURCE_SHA}",
        "SOURCE_SHA": SOURCE_SHA,
        "MIGRATION_HEAD": "069_ai_cohort_and_transactional_outbox.sql",
        "ARTIFACT_SHA256": ARTIFACT_SHA,
        "SBOM_SHA256": SBOM_SHA,
        "PREDECESSOR_RELEASE_ID": f"retail-release-{OLD_SHA}",
        "PREDECESSOR_SHA": OLD_SHA,
        "ROLLBACK_RELEASE_ID": f"retail-release-{OLD_SHA}",
        "ROLLBACK_SHA": OLD_SHA,
        "DEPLOYED_AT_UTC": "2026-08-22T12:34:56Z",
        "OLD_SHA": OLD_SHA,
        "NEW_SHA": SOURCE_SHA,
        "STATE": "deployed",
        "UPDATED_AT": "2026-08-22T12:35:01Z",
    }


def write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    path = tmp_path / "release.env"
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    return path


def test_valid_d2_promotion_renders_non_authoritative_view(tmp_path: Path) -> None:
    values = release_notes.parse_release_env(write_env(tmp_path, valid_values()))
    rendered = release_notes.render_markdown(values)

    assert "Generated view — not production authority" in rendered
    assert f"`retail-release-{SOURCE_SHA}`" in rendered
    assert f"`production/retail-release-{SOURCE_SHA}`" in rendered
    assert f"`{ARTIFACT_SHA}`" in rendered
    assert f"`{SBOM_SHA}`" in rendered
    assert "`069_ai_cohort_and_transactional_outbox.sql`" in rendered
    assert "repository-managed `current`/`latest` release" in rendered


def test_parser_rejects_duplicate_missing_and_unknown_fields(tmp_path: Path) -> None:
    values = valid_values()
    path = write_env(tmp_path, values)
    path.write_text(path.read_text(encoding="utf-8") + f"SOURCE_SHA={SOURCE_SHA}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate field: SOURCE_SHA"):
        release_notes.parse_release_env(path)

    values = valid_values()
    values.pop("SBOM_SHA256")
    with pytest.raises(ValueError, match="missing required field.*SBOM_SHA256"):
        release_notes.parse_release_env(write_env(tmp_path, values))

    values = valid_values()
    values["FUTURE_D2_FIELD"] = "must-not-be-silently-ignored"
    with pytest.raises(ValueError, match="unknown schema-v1 field.*FUTURE_D2_FIELD"):
        release_notes.parse_release_env(write_env(tmp_path, values))


def test_renderer_accepts_only_complete_deployed_d2_state() -> None:
    values = valid_values()
    values["PROMOTION_SCHEMA_VERSION"] = "2"
    with pytest.raises(ValueError, match="PROMOTION_SCHEMA_VERSION"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["STATE"] = "rolled_back"
    with pytest.raises(ValueError, match="STATE=deployed"):
        release_notes.validate_deployed_promotion(values)


def test_source_and_release_relations_fail_closed() -> None:
    values = valid_values()
    values["NEW_SHA"] = "e" * 40
    with pytest.raises(ValueError, match="NEW_SHA must equal SOURCE_SHA"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["RELEASE_ID"] = "retail-release-" + "e" * 40
    with pytest.raises(ValueError, match="RELEASE_ID"):
        release_notes.validate_deployed_promotion(values)


def test_predecessor_and_rollback_relations_fail_closed() -> None:
    values = valid_values()
    values["PREDECESSOR_SHA"] = "e" * 40
    values["PREDECESSOR_RELEASE_ID"] = "retail-release-" + "e" * 40
    with pytest.raises(ValueError, match="PREDECESSOR_SHA must equal OLD_SHA"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["ROLLBACK_SHA"] = "e" * 40
    values["ROLLBACK_RELEASE_ID"] = "retail-release-" + "e" * 40
    with pytest.raises(ValueError, match="ROLLBACK_SHA must equal OLD_SHA"):
        release_notes.validate_deployed_promotion(values)


def test_invalid_sha_digest_and_migration_formats_fail_closed() -> None:
    values = valid_values()
    values["OLD_SHA"] = "not-a-sha"
    with pytest.raises(ValueError, match="OLD_SHA"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["ARTIFACT_SHA256"] = "not-a-digest"
    with pytest.raises(ValueError, match="ARTIFACT_SHA256"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["MIGRATION_HEAD"] = "69_bad.sql"
    with pytest.raises(ValueError, match="MIGRATION_HEAD"):
        release_notes.validate_deployed_promotion(values)


def test_invalid_or_noncanonical_utc_timestamp_fails_closed() -> None:
    values = valid_values()
    values["DEPLOYED_AT_UTC"] = "2026-99-99T99:99:99Z"
    with pytest.raises(ValueError, match="valid UTC timestamp"):
        release_notes.validate_deployed_promotion(values)

    values = valid_values()
    values["UPDATED_AT"] = "2026-08-22T12:35:01+00:00"
    with pytest.raises(ValueError, match="canonical UTC format"):
        release_notes.validate_deployed_promotion(values)


def test_symlink_release_env_is_rejected(tmp_path: Path) -> None:
    target = write_env(tmp_path, valid_values())
    link = tmp_path / "release-link.env"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="missing or unsafe"):
        release_notes.parse_release_env(link)
