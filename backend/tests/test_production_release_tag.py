from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts/create_production_release_tag.py"
SPEC = importlib.util.spec_from_file_location("create_production_release_tag", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_tag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_tag)

SOURCE_SHA = "a" * 40
ARTIFACT_SHA = "b" * 64
SBOM_SHA = "c" * 64
MIGRATION_HEAD = "069_ai_cohort_and_transactional_outbox.sql"
RELEASE_ID = f"retail-release-{SOURCE_SHA}"
TAG_NAME = f"production/{RELEASE_ID}"
TAG_OBJECT_SHA = "d" * 40


def identity() -> dict[str, str]:
    return release_tag.validate_release_identity(
        source_sha=SOURCE_SHA,
        release_id=RELEASE_ID,
        migration_head=MIGRATION_HEAD,
        artifact_sha256=ARTIFACT_SHA,
        sbom_sha256=SBOM_SHA,
    )


def annotated_tag_payload(
    *,
    source_sha: str = SOURCE_SHA,
    artifact_sha256: str = ARTIFACT_SHA,
    ci_run_id: str = "111",
    deploy_run_id: str = "222",
) -> dict[str, Any]:
    tag_identity = identity().copy()
    tag_identity["sourceSha"] = source_sha
    tag_identity["artifactSha256"] = artifact_sha256
    message = release_tag.build_tag_message(
        tag_identity,
        ci_run_id=ci_run_id,
        deploy_run_id=deploy_run_id,
    )
    return {
        "sha": TAG_OBJECT_SHA,
        "tag": TAG_NAME,
        "message": message,
        "object": {"type": "commit", "sha": source_sha},
    }


def ref_payload(*, object_type: str = "tag", sha: str = TAG_OBJECT_SHA) -> dict[str, Any]:
    return {
        "ref": f"refs/tags/{TAG_NAME}",
        "object": {"type": object_type, "sha": sha},
    }


def test_production_tag_name_is_bound_to_d2_release_id() -> None:
    assert release_tag.production_tag_name(identity()) == TAG_NAME
    with pytest.raises(ValueError, match="releaseId must equal"):
        release_tag.validate_release_identity(
            source_sha=SOURCE_SHA,
            release_id="retail-release-" + "f" * 40,
            migration_head=MIGRATION_HEAD,
            artifact_sha256=ARTIFACT_SHA,
            sbom_sha256=SBOM_SHA,
        )


def test_tag_message_is_canonical_machine_readable_identity() -> None:
    message = release_tag.build_tag_message(identity(), ci_run_id="123", deploy_run_id="456")
    payload = json.loads(message)
    assert payload == {
        "schemaVersion": 1,
        "kind": "unihub-retail-production-promotion",
        "sourceSha": SOURCE_SHA,
        "releaseId": RELEASE_ID,
        "migrationHead": MIGRATION_HEAD,
        "artifactSha256": ARTIFACT_SHA,
        "sbomSha256": SBOM_SHA,
        "ciRunId": "123",
        "deployRunId": "456",
    }
    assert release_tag.verify_tag_message(message, identity()) == payload


def test_existing_matching_annotated_tag_is_idempotent_across_retries() -> None:
    calls: list[tuple[str, str]] = []

    def request(method: str, path: str, token: str, payload: dict[str, Any] | None):
        calls.append((method, path))
        assert token == "token"
        if "/git/ref/tags/" in path:
            return ref_payload()
        if f"/git/tags/{TAG_OBJECT_SHA}" in path:
            # The existing tag records the first promotion. A later workflow
            # retry may have different run IDs and must not rewrite the tag.
            return annotated_tag_payload(ci_run_id="10", deploy_run_id="20")
        raise AssertionError((method, path, payload))

    status, tag_name = release_tag.ensure_production_tag(
        repository="owner/repo",
        token="token",
        identity=identity(),
        ci_run_id="999",
        deploy_run_id="1000",
        request=request,
    )
    assert (status, tag_name) == ("existing", TAG_NAME)
    assert all(method == "GET" for method, _ in calls)


def test_existing_lightweight_tag_fails_closed() -> None:
    def request(method: str, path: str, token: str, payload: dict[str, Any] | None):
        assert method == "GET"
        return ref_payload(object_type="commit", sha=SOURCE_SHA)

    with pytest.raises(ValueError, match="annotated, not lightweight"):
        release_tag.ensure_production_tag(
            repository="owner/repo",
            token="token",
            identity=identity(),
            ci_run_id="1",
            deploy_run_id="2",
            request=request,
        )


def test_existing_annotated_tag_with_conflicting_identity_fails_closed() -> None:
    def request(method: str, path: str, token: str, payload: dict[str, Any] | None):
        if "/git/ref/tags/" in path:
            return ref_payload()
        if f"/git/tags/{TAG_OBJECT_SHA}" in path:
            return annotated_tag_payload(artifact_sha256="e" * 64)
        raise AssertionError((method, path, payload))

    with pytest.raises(ValueError, match="identity mismatch: artifactSha256"):
        release_tag.ensure_production_tag(
            repository="owner/repo",
            token="token",
            identity=identity(),
            ci_run_id="1",
            deploy_run_id="2",
            request=request,
        )


def test_missing_tag_creates_annotated_object_then_immutable_ref() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    ref_exists = False

    def request(method: str, path: str, token: str, payload: dict[str, Any] | None):
        nonlocal ref_exists
        calls.append((method, path, payload))
        if method == "GET" and "/git/ref/tags/" in path:
            if not ref_exists:
                raise release_tag.GitHubApiError(404, "not found")
            return ref_payload()
        if method == "POST" and path.endswith("/git/tags"):
            assert payload is not None
            assert payload["tag"] == TAG_NAME
            assert payload["object"] == SOURCE_SHA
            assert payload["type"] == "commit"
            parsed = json.loads(payload["message"])
            assert parsed["ciRunId"] == "123"
            assert parsed["deployRunId"] == "456"
            return {"sha": TAG_OBJECT_SHA}
        if method == "POST" and path.endswith("/git/refs"):
            assert payload == {"ref": f"refs/tags/{TAG_NAME}", "sha": TAG_OBJECT_SHA}
            ref_exists = True
            return {"ref": f"refs/tags/{TAG_NAME}"}
        if method == "GET" and f"/git/tags/{TAG_OBJECT_SHA}" in path:
            return annotated_tag_payload(ci_run_id="123", deploy_run_id="456")
        raise AssertionError((method, path, payload))

    status, tag_name = release_tag.ensure_production_tag(
        repository="owner/repo",
        token="token",
        identity=identity(),
        ci_run_id="123",
        deploy_run_id="456",
        request=request,
    )
    assert (status, tag_name) == ("created", TAG_NAME)
    assert [method for method, _, _ in calls].count("POST") == 2


def test_ref_creation_race_is_accepted_only_after_strict_reverification() -> None:
    first_get = True

    def request(method: str, path: str, token: str, payload: dict[str, Any] | None):
        nonlocal first_get
        if method == "GET" and "/git/ref/tags/" in path:
            if first_get:
                first_get = False
                raise release_tag.GitHubApiError(404, "not found")
            return ref_payload()
        if method == "POST" and path.endswith("/git/tags"):
            return {"sha": TAG_OBJECT_SHA}
        if method == "POST" and path.endswith("/git/refs"):
            raise release_tag.GitHubApiError(422, "ref already exists")
        if method == "GET" and f"/git/tags/{TAG_OBJECT_SHA}" in path:
            return annotated_tag_payload(ci_run_id="7", deploy_run_id="8")
        raise AssertionError((method, path, payload))

    status, tag_name = release_tag.ensure_production_tag(
        repository="owner/repo",
        token="token",
        identity=identity(),
        ci_run_id="7",
        deploy_run_id="8",
        request=request,
    )
    assert (status, tag_name) == ("created", TAG_NAME)


def test_malformed_existing_tag_message_and_repository_are_rejected() -> None:
    with pytest.raises(ValueError, match="owner/name"):
        release_tag.ensure_production_tag(
            repository="not-a-repository",
            token="token",
            identity=identity(),
            ci_run_id="1",
            deploy_run_id="2",
            request=lambda *_: {},
        )

    with pytest.raises(ValueError, match="not valid JSON"):
        release_tag.verify_tag_message("not-json", identity())


def test_invalid_identity_formats_fail_before_any_api_call() -> None:
    with pytest.raises(ValueError, match="migrationHead"):
        release_tag.validate_release_identity(
            source_sha=SOURCE_SHA,
            release_id=RELEASE_ID,
            migration_head="69_bad.sql",
            artifact_sha256=ARTIFACT_SHA,
            sbom_sha256=SBOM_SHA,
        )
    with pytest.raises(ValueError, match="artifactSha256"):
        release_tag.validate_release_identity(
            source_sha=SOURCE_SHA,
            release_id=RELEASE_ID,
            migration_head=MIGRATION_HEAD,
            artifact_sha256="not-a-digest",
            sbom_sha256=SBOM_SHA,
        )


def test_deploy_workflow_isolates_repository_write_after_successful_main_deploy() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github/workflows/deploy.yml"
    ).read_text(encoding="utf-8")

    assert "permissions:\n  actions: read\n  contents: read\n" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "id: release_identity" in workflow

    tag_job = workflow.split("\n  tag-promoted-release:\n", 1)[1]
    assert "needs: deploy" in tag_job
    assert "if: needs.deploy.result == 'success'" in tag_job
    assert "runs-on: ubuntu-latest" in tag_job
    assert "permissions:\n      contents: write" in tag_job
    assert "ref: ${{ github.sha }}" in tag_job
    assert "persist-credentials: false" in tag_job
    assert "scripts/create_production_release_tag.py" in tag_job

    deploy_job = workflow.split("\n  tag-promoted-release:\n", 1)[0]
    assert "contents: write" not in deploy_job
