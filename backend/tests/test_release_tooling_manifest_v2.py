from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_IDENTITY_PATH = REPO_ROOT / "scripts" / "release_identity.py"
DEPLOY_SCRIPT_PATH = REPO_ROOT / "ops" / "deploy-retail-artifact.sh"


def _load_release_identity():
    spec = importlib.util.spec_from_file_location(
        "release_identity", RELEASE_IDENTITY_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline(migrations: dict[str, str]) -> dict[str, str]:
    first = sorted(migrations.keys())[0]
    return {
        "file": "schema_v2.sql",
        "sha256": "a" * 64,
        "incorporated_through": first,
    }


def _migrations(n: int = 2) -> dict[str, str]:
    return {f"{i:03d}_mig.sql": "f" * 64 for i in range(1, n + 1)}


def _payload(
    *,
    version: int = 2,
    migrations: dict[str, str] | None = None,
    execution_modes: dict[str, str] | None = None,
    execution_classes: object = ...,
    include_execution_classes: bool = True,
) -> dict[str, object]:
    m = migrations if migrations is not None else _migrations()
    payload: dict[str, object] = {
        "version": version,
        "baseline": _baseline(m),
        "migrations": m,
    }
    if execution_modes is not None:
        payload["execution_modes"] = execution_modes
    if include_execution_classes:
        # Caller passed an explicit value (including None) — use it as-is.
        if execution_classes is not ...:
            payload["execution_classes"] = execution_classes
        # No value passed: provide a sensible default per version so the
        # payload validates.
        elif version == 2:
            payload["execution_classes"] = {name: "transactional" for name in m}
        # version == 1 with no execution_classes argument: omit the key.
    return payload


# ---------------------------------------------------------------------------
# scripts/release_identity.py coverage
# ---------------------------------------------------------------------------


def test_release_identity_validates_v1_legacy_without_execution_classes() -> None:
    m = _load_release_identity()
    payload = _payload(version=1, include_execution_classes=False)
    # Must not raise.
    m._validate_migration_payload(payload)


def test_release_identity_accepts_v2_with_exhaustive_execution_classes() -> None:
    m = _load_release_identity()
    migrations = _migrations(3)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={name: "transactional" for name in migrations},
    )
    m._validate_migration_payload(payload)


def test_release_identity_rejects_v2_missing_execution_classes() -> None:
    m = _load_release_identity()
    payload = _payload(version=2, include_execution_classes=False)
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_v2_null_execution_classes() -> None:
    m = _load_release_identity()
    payload = _payload(version=2, execution_classes=None)
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_v2_non_dict_execution_classes() -> None:
    m = _load_release_identity()
    payload = _payload(version=2, execution_classes=["transactional"])
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_invalid_execution_class_value() -> None:
    m = _load_release_identity()
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={keys[0]: "bogus", keys[1]: "transactional"},
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_incomplete_execution_classes_map() -> None:
    m = _load_release_identity()
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={keys[0]: "transactional"},  # missing keys[1]
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_extra_execution_classes_key() -> None:
    m = _load_release_identity()
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={
            keys[0]: "transactional",
            keys[1]: "transactional",
            "999_extra.sql": "transactional",
        },
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_online_classification_mismatch() -> None:
    m = _load_release_identity()
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_modes={keys[0]: "online"},
        execution_classes={
            keys[0]: "online",
            keys[1]: "online",  # mismatched: not in execution_modes
        },
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


def test_release_identity_rejects_unsupported_version_3() -> None:
    m = _load_release_identity()
    payload = _payload(
        version=3,
        execution_classes={next(iter(_migrations(1))): "transactional"},
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


@pytest.mark.parametrize("bad_version", [True, False, 1.0, 2.0, "1", "2", None])
def test_release_identity_rejects_non_integer_version(
    bad_version: object,
) -> None:
    """Release-identity validation MUST reject non-integer ``version``
    values, including JSON booleans (``true``/``false``) and floats
    (``1.0``/``2.0``)."""
    m = _load_release_identity()
    migrations = _migrations(1)
    payload = _payload(
        version=bad_version,  # type: ignore[arg-type]
        migrations=migrations,
        execution_classes={next(iter(migrations)): "transactional"},
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


@pytest.mark.parametrize("bad_version", [True, False, 1.0, 2.0, "1", "2", None])
def test_deploy_script_rejects_non_integer_version(
    tmp_path, deploy_validator, bad_version: object
) -> None:
    """The deploy-script inline validator MUST reject the same non-integer
    versions that the release-identity helper and the migration runner
    reject."""
    migrations = _migrations(1)
    payload = _payload(
        version=bad_version,  # type: ignore[arg-type]
        migrations=migrations,
        execution_classes={next(iter(migrations)): "transactional"},
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_release_identity_current_repo_manifest_is_v2() -> None:
    """The active repository manifest is v2 and is accepted by the
    formal release-identity validator."""
    m = _load_release_identity()
    payload = json.loads(
        (REPO_ROOT / "backend/db/migrations/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["version"] == 2
    # Must not raise.
    m._validate_migration_payload(payload)


def test_release_identity_v1_with_explicit_classes_is_still_validated() -> None:
    """A v1 manifest that opts into F4 by providing a valid
    execution_classes dict is still validated against the same rules."""
    m = _load_release_identity()
    migrations = _migrations(2)
    payload = _payload(
        version=1,
        migrations=migrations,
        execution_classes={name: "transactional" for name in migrations},
    )
    m._validate_migration_payload(payload)


def test_release_identity_v1_with_bogus_class_is_rejected() -> None:
    m = _load_release_identity()
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=1,
        migrations=migrations,
        execution_classes={keys[0]: "bogus", keys[1]: "transactional"},
    )
    with pytest.raises(ValueError, match="invalid migration manifest"):
        m._validate_migration_payload(payload)


# ---------------------------------------------------------------------------
# ops/deploy-retail-artifact.sh inline validator coverage
# ---------------------------------------------------------------------------


def _extract_heredoc(start_marker: str, sentinels: tuple[str, ...], stop_at: str | None = None) -> str:
    """Extract the Python code of the next heredoc after ``start_marker``
    in the deploy script. The heredoc body starts on the line after
    ``start_marker`` and ends at the next line that matches one of
    ``sentinels`` (e.g. ``PY``). If ``stop_at`` is given, the extraction
    also stops at the first occurrence of that substring (used to skip the
    trailing try/except comparison block which would otherwise try to read
    ``sys.argv``)."""
    text = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")
    pos = text.index(start_marker)
    newline = text.index("\n", pos)
    body_start = newline + 1
    sentinel_pattern = r"(?m)^(" + "|".join(re.escape(s) for s in sentinels) + r")$"
    match = re.search(sentinel_pattern, text[body_start:])
    assert match is not None, f"sentinel not found after {start_marker!r}"
    body_end = body_start + match.start()
    body = text[body_start:body_end]
    if stop_at is not None:
        idx = body.index(stop_at)
        body = body[:idx]
    return body


_HEREDOC = _extract_heredoc(
    'if ! "$PYTHON_BASE" -I -S - "$current_manifest" "$target_manifest" <<\'PY\'',
    ("PY",),
    stop_at="\ntry:\n",
)


@pytest.fixture(scope="module")
def deploy_validator():
    """Compile the inline heredoc and expose its load()/validate symbols."""
    namespace: dict = {}
    exec(_HEREDOC, namespace)
    return namespace


def _write_manifest(tmp_path: Path, payload: dict[str, object], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_deploy_script_heredoc_compiles(deploy_validator) -> None:
    assert callable(deploy_validator["load"])
    assert callable(deploy_validator["_validate"])


def test_deploy_script_v1_legacy_without_execution_classes_is_accepted(
    tmp_path, deploy_validator
) -> None:
    path = _write_manifest(tmp_path, _payload(version=1, include_execution_classes=False), "m.json")
    deploy_validator["load"](str(path))  # must not raise


def test_deploy_script_v2_exhaustive_execution_classes_is_accepted(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(3)
    path = _write_manifest(
        tmp_path,
        _payload(
            version=2,
            migrations=migrations,
            execution_classes={name: "transactional" for name in migrations},
        ),
        "m.json",
    )
    deploy_validator["load"](str(path))


def test_deploy_script_v2_missing_execution_classes_is_rejected(
    tmp_path, deploy_validator
) -> None:
    path = _write_manifest(tmp_path, _payload(version=2, include_execution_classes=False), "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_v2_null_execution_classes_is_rejected(
    tmp_path, deploy_validator
) -> None:
    path = _write_manifest(tmp_path, _payload(version=2, execution_classes=None), "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_v2_non_dict_execution_classes_is_rejected(
    tmp_path, deploy_validator
) -> None:
    path = _write_manifest(tmp_path, _payload(version=2, execution_classes=["t"]), "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_invalid_execution_class_value_is_rejected(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={keys[0]: "bogus", keys[1]: "transactional"},
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_incomplete_execution_classes_is_rejected(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={keys[0]: "transactional"},
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_extra_execution_classes_key_is_rejected(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={
            keys[0]: "transactional",
            keys[1]: "transactional",
            "999_extra.sql": "transactional",
        },
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_online_execution_modes_mismatch_is_rejected(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(2)
    keys = list(migrations)
    payload = _payload(
        version=2,
        migrations=migrations,
        execution_modes={keys[0]: "online"},
        execution_classes={
            keys[0]: "online",
            keys[1]: "online",
        },
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_unsupported_version_3_is_rejected(
    tmp_path, deploy_validator
) -> None:
    migrations = _migrations(1)
    payload = _payload(
        version=3,
        migrations=migrations,
        execution_classes={next(iter(migrations)): "transactional"},
    )
    path = _write_manifest(tmp_path, payload, "m.json")
    with pytest.raises(ValueError, match="invalid migration manifest"):
        deploy_validator["load"](str(path))


def test_deploy_script_current_repo_manifest_is_accepted(deploy_validator) -> None:
    """The active repository v2 manifest passes the deploy-script
    inline validator."""
    repo_manifest = REPO_ROOT / "backend/db/migrations/manifest.json"
    payload = json.loads(repo_manifest.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    # Must not raise.
    deploy_validator["load"](str(repo_manifest))


def test_release_identity_and_deploy_script_share_validation_outcomes(
    tmp_path, deploy_validator
) -> None:
    """The two formal consumers MUST agree on every contract decision:
    every manifest accepted by one MUST be accepted by the other, and
    every manifest rejected by one MUST be rejected by the other."""
    release_identity = _load_release_identity()

    cases = [
        # (description, payload-builder, accepted)
        (
            "v1 legacy absent execution_classes",
            lambda: _payload(version=1, include_execution_classes=False),
            True,
        ),
        (
            "v2 exhaustive execution_classes",
            lambda: _payload(
                version=2,
                execution_classes={
                    name: "transactional" for name in _migrations(2)
                },
            ),
            True,
        ),
        (
            "v2 missing execution_classes",
            lambda: _payload(version=2, include_execution_classes=False),
            False,
        ),
        (
            "v2 null execution_classes",
            lambda: _payload(version=2, execution_classes=None),
            False,
        ),
        (
            "v2 non-dict execution_classes",
            lambda: _payload(version=2, execution_classes=["t"]),
            False,
        ),
        (
            "invalid execution_class value",
            lambda: _payload(
                version=2,
                execution_classes={
                    list(_migrations(2))[0]: "bogus",
                    list(_migrations(2))[1]: "transactional",
                },
            ),
            False,
        ),
        (
            "incomplete execution_classes",
            lambda: _payload(
                version=2,
                execution_classes={list(_migrations(2))[0]: "transactional"},
            ),
            False,
        ),
        (
            "extra execution_classes key",
            lambda: _payload(
                version=2,
                execution_classes={
                    list(_migrations(2))[0]: "transactional",
                    list(_migrations(2))[1]: "transactional",
                    "999_extra.sql": "transactional",
                },
            ),
            False,
        ),
        (
            "online/execution_modes mismatch",
            lambda: _payload(
                version=2,
                execution_modes={list(_migrations(2))[0]: "online"},
                execution_classes={
                    list(_migrations(2))[0]: "online",
                    list(_migrations(2))[1]: "online",
                },
            ),
            False,
        ),
        (
            "unsupported version 3",
            lambda: _payload(
                version=3,
                execution_classes={list(_migrations(1))[0]: "transactional"},
            ),
            False,
        ),
        (
            "bool True as version (== 1 in Python)",
            lambda: _payload(
                version=True,
                execution_classes={
                    list(_migrations(2))[0]: "transactional",
                    list(_migrations(2))[1]: "transactional",
                },
            ),
            False,
        ),
        (
            "float 1.0 as version (== 1 in Python)",
            lambda: _payload(
                version=1.0,
                execution_classes={
                    list(_migrations(2))[0]: "transactional",
                    list(_migrations(2))[1]: "transactional",
                },
            ),
            False,
        ),
        (
            "float 2.0 as version",
            lambda: _payload(
                version=2.0,
                execution_classes={
                    list(_migrations(2))[0]: "transactional",
                    list(_migrations(2))[1]: "transactional",
                },
            ),
            False,
        ),
    ]

    def _release_identity_accepts(payload: dict[str, object]) -> bool:
        try:
            release_identity._validate_migration_payload(payload)
            return True
        except ValueError:
            return False

    def _deploy_script_accepts(payload: dict[str, object], tmp_path: Path) -> bool:
        path = _write_manifest(tmp_path, payload, "m.json")
        try:
            deploy_validator["load"](str(path))
            return True
        except (ValueError, OSError):
            return False

    for description, build, accepted in cases:
        payload = build()
        ri_ok = _release_identity_accepts(payload)
        ds_ok = _deploy_script_accepts(payload, tmp_path)
        assert ri_ok == ds_ok, (
            f"formal consumers disagree on {description!r}: "
            f"release_identity={ri_ok} deploy_script={ds_ok}"
        )
        assert ri_ok is accepted, (
            f"unexpected outcome on {description!r}: accepted={accepted}"
        )


# ---------------------------------------------------------------------------
# F4 v2 rollout rollback-compatibility canonicalization
# ---------------------------------------------------------------------------


# Public repository commit used as the historical v1 rollout fixture.
_BASE_SHA = "d3ee8a6679120f69c2ced992798294c9b5512253"  # pragma: allowlist secret


def _base_v1_manifest_bytes() -> bytes:
    import subprocess

    return subprocess.check_output(
        ["git", "show", f"{_BASE_SHA}:backend/db/migrations/manifest.json"],
        cwd=str(REPO_ROOT),
    )


def test_rollback_compat_real_base_v1_equals_real_current_v2(deploy_validator) -> None:
    """A. Real transition: the base v1 manifest (d3ee8a6) and the current
    candidate v2 manifest MUST be rollback-compatible: their canonical
    representations compare equal because they share baseline, migrations,
    checksums, and per-migration execution classes."""
    base_payload = json.loads(_base_v1_manifest_bytes())
    current_payload = json.loads(
        (REPO_ROOT / "backend/db/migrations/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert base_payload["version"] == 1
    assert current_payload["version"] == 2
    assert "execution_classes" not in base_payload
    assert set(current_payload["execution_classes"]) == set(
        current_payload["migrations"]
    )

    base_canonical = deploy_validator["_canonical"](base_payload)
    current_canonical = deploy_validator["_canonical"](current_payload)
    assert base_canonical == current_canonical, (
        "base v1 and current v2 must canonicalize identically"
    )


def test_rollback_compat_synthetic_v1_with_online_equals_v2_with_online(
    deploy_validator,
) -> None:
    """B. A v1 manifest that declares an explicit ``online`` execution_mode
    canonicalizes to the same per-migration classification as the
    equivalent v2 manifest with an exhaustive execution_classes map."""
    migrations = _migrations(2)
    keys = list(migrations)
    v1_payload = _payload(
        version=1,
        migrations=migrations,
        execution_modes={keys[1]: "online"},
        include_execution_classes=False,
    )
    v2_payload = _payload(
        version=2,
        migrations=migrations,
        execution_modes={keys[1]: "online"},
        execution_classes={keys[0]: "transactional", keys[1]: "online"},
    )
    assert deploy_validator["_canonical"](v1_payload) == deploy_validator[
        "_canonical"
    ](v2_payload)


def test_rollback_compat_v2_maintenance_window_blocked_from_v1_inferred_tx(
    deploy_validator,
) -> None:
    """C. v2 maintenance-window classification is NOT equivalent to legacy
    v1 inferred transactional: the canonical view differs and a rollback
    from the maintenance-window release to the previous v1 release must
    fail closed."""
    migrations = _migrations(2)
    keys = list(migrations)
    v1_payload = _payload(
        version=1,
        migrations=migrations,
        include_execution_classes=False,
    )
    v2_payload = _payload(
        version=2,
        migrations=migrations,
        execution_classes={
            keys[0]: "transactional",
            keys[1]: "maintenance-window",
        },
    )
    assert deploy_validator["_canonical"](v1_payload) != deploy_validator[
        "_canonical"
    ](v2_payload)


def test_rollback_compat_checksum_mismatch_remains_blocked(deploy_validator) -> None:
    """D. A checksum difference between the deployed release and the
    rollback target MUST still block rollback even after canonicalization."""
    migrations = _migrations(2)
    current = _payload(version=2, migrations=migrations)
    target = _payload(version=2, migrations=migrations)
    target["migrations"] = dict(target["migrations"])
    first_key = next(iter(target["migrations"]))
    # Flip a single character of the checksum.
    flipped = "f" if target["migrations"][first_key][0] != "f" else "0"
    target["migrations"][first_key] = (
        flipped + target["migrations"][first_key][1:]
    )
    assert deploy_validator["_canonical"](current) != deploy_validator[
        "_canonical"
    ](target)


def test_rollback_compat_baseline_mismatch_remains_blocked(deploy_validator) -> None:
    """E. A baseline difference between the deployed release and the
    rollback target MUST still block rollback even after canonicalization."""
    current = _payload(version=2)
    target = _payload(version=2)
    target["baseline"] = dict(target["baseline"])
    target["baseline"]["file"] = "schema_v3.sql"
    target["baseline"]["sha256"] = "e" * 64
    assert deploy_validator["_canonical"](current) != deploy_validator[
        "_canonical"
    ](target)


def test_rollback_compat_unknown_metadata_mismatch_remains_blocked(
    deploy_validator,
) -> None:
    """F. An unknown metadata field added to one manifest MUST still block
    rollback after canonicalization: canonicalization must NOT silently
    drop unrelated fields. The canonical view starts from ``dict(payload)``
    and only normalizes the three representation fields."""
    current = _payload(version=2)
    target = _payload(version=2)
    target["some_unknown_metadata"] = "extra"
    assert deploy_validator["_canonical"](current) != deploy_validator[
        "_canonical"
    ](target)


def test_rollback_compat_malformed_and_non_integer_versions_still_rejected(
    deploy_validator,
) -> None:
    """G. The previous fail-closed semantics MUST remain intact: the
    canonicalization wrapper still calls the strict validator, so
    malformed/non-integer versions are rejected before any comparison."""
    migrations = _migrations(1)
    key = next(iter(migrations))
    for bad_version in (True, 1.0, 2.0, "1", None):
        payload = _payload(
            version=bad_version,  # type: ignore[arg-type]
            migrations=migrations,
            execution_classes={key: "transactional"},
        )
        with pytest.raises(ValueError, match="invalid migration manifest"):
            deploy_validator["_canonical"](payload)
