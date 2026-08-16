#!/usr/bin/env python3
"""check_high_risk_pr_governance.py

Stdlib-only checker for high-risk PR governance (A3 v2, revision round 1).

Design:
- Deterministic path matching only (exact + prefix). No glob, no fnmatch.
- Reads .github/governance/high-risk-paths.json (manifest).
- Fetches files changed in a PR via GitHub REST API with pagination and a
  3000-file hard ceiling (fail-closed if exceeded).
- Reads PR body from GITHUB_EVENT_PATH.
- If no high-risk path is changed -> PASS without metadata.
- If high-risk paths are changed, requires (each appears EXACTLY ONCE):
    Governance-Categories:    <comma-separated canonical category names>
    Governance-Justification: <text, >=20 non-whitespace chars, not a placeholder>
    Governance-Validation:    <text, >=20 non-whitespace chars, not a placeholder>
  Duplicate categories, unknown categories, missing/short/placeholder values
  all FAIL.
- Mock mode is only for local tests. In GITHUB_ACTIONS=true, any GOVERNANCE_MOCK_*
  environment variable -> FAIL immediately.
- Fail-closed on invalid manifest, API HTTP error, malformed JSON, schema error,
  pagination failure, 3000-file ceiling exceeded.
- PR body is DATA only; parsed by Python regex, never executed as shell/regex/eval.

Test injection:
- Module-level _get_pr_files_page(repo, pr_number, page, token) can be
  monkey-patched by tests to simulate API responses (success, 4xx/5xx,
  malformed JSON, 3000+ files, paginated data with high-risk on a later page).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

# ---------- constants ----------

MANIFEST_PATH = ".github/governance/high-risk-paths.json"

KNOWN_CATEGORIES = frozenset({
    "auth-identity",
    "migrations-db-authority",
    "deploy-release-ci",
    "salary-private-identity",
    "target-calculator",
})

INVALID_FILLER = frozenset({
    "n/a", "na", "none", "todo", "tbd", "xxx", "-", "--", "placeholder", "filler"
})

MIN_JUSTIFICATION_CHARS = 20
MAX_FILES = 3000
PAGE_SIZE = 100

_FIELDS = ("Governance-Categories", "Governance-Justification", "Governance-Validation")


# ---------- logging ----------

def _fail(msg: str) -> "NoReturn":
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _info(msg: str) -> None:
    print(msg)


# ---------- mock safety ----------

def _check_mock_safety() -> None:
    """In GitHub Actions, any GOVERNANCE_MOCK_* environment variable is forbidden."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return
    bad = sorted(k for k in os.environ if k.startswith("GOVERNANCE_MOCK_"))
    if bad:
        _fail(f"GITHUB_ACTIONS=true but mock env var(s) set: {bad}")


# ---------- manifest ----------

def _load_manifest(repo_root: str) -> dict:
    p = pathlib.Path(repo_root) / MANIFEST_PATH
    if not p.exists():
        _fail(f"manifest not found at {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail(f"manifest is not valid JSON: {e}")
    if not isinstance(data, dict):
        _fail("manifest root must be a JSON object")
    cats = data.get("categories")
    if not isinstance(cats, dict) or not cats:
        _fail("manifest must define a non-empty 'categories' object")
    for name, body in cats.items():
        if not isinstance(body, dict):
            _fail(f"manifest category '{name}' must be an object")
        paths = body.get("paths")
        if (not isinstance(paths, list) or not paths
                or not all(isinstance(x, str) and x for x in paths)):
            _fail(f"manifest category '{name}' must have a non-empty 'paths' list of strings")
        for entry in paths:
            if any(c in entry for c in ("*", "?", "[", "]")):
                _fail(f"manifest category '{name}' uses glob syntax: {entry!r}")
    return data


# ---------- deterministic matching (no glob) ----------

def _is_prefix(entry: str) -> bool:
    return entry.endswith("/")


def _match(changed: str, entry: str) -> bool:
    if _is_prefix(entry):
        return changed.startswith(entry)
    return changed == entry


def _detect(manifest: dict, changed_files: list) -> dict:
    """Return {category: [matched_files]} for categories with >=1 match.
    Deterministic dedupe (preserves first-seen order)."""
    hits: dict = {}
    for cat, body in manifest["categories"].items():
        matched: list = []
        for f in changed_files:
            for entry in body["paths"]:
                if _match(f, entry):
                    matched.append(f)
                    break
        if matched:
            seen: set = set()
            deduped: list = []
            for f in matched:
                if f not in seen:
                    seen.add(f)
                    deduped.append(f)
            hits[cat] = deduped
    return hits


# ---------- event ----------

def _read_event(event_path: str) -> dict:
    if not event_path or not os.path.isfile(event_path):
        _fail(f"GITHUB_EVENT_PATH ({event_path!r}) not found or not a file")
    try:
        ev = json.loads(open(event_path, encoding="utf-8").read())
    except Exception as e:
        _fail(f"GITHUB_EVENT_PATH not parseable JSON: {e}")
    if not isinstance(ev, dict):
        _fail("event payload is not a JSON object")
    pr = ev.get("pull_request")
    if not isinstance(pr, dict):
        _fail("event is not a pull_request event")
    return pr


def _read_body_from_event(event_path: str) -> str:
    if not event_path or not os.path.isfile(event_path):
        return ""
    try:
        ev = json.loads(open(event_path, encoding="utf-8").read())
    except Exception:
        return ""
    if not isinstance(ev, dict):
        return ""
    pr = ev.get("pull_request")
    if not isinstance(pr, dict):
        return ""
    body = pr.get("body")
    return body if isinstance(body, str) else ""


# ---------- API (paginated; module-level for test injection) ----------

def _get_pr_files_page(repo: str, pr_number: int, page: int, token: str):
    """Fetch one page of /pulls/{n}/files. Returns a list of dicts (raw API rows).
    Raises on HTTP/network/JSON failure. Tests monkey-patch this."""
    url = (f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
           f"?per_page={PAGE_SIZE}&page={page}")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "unihub-retail-governance-checker",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        body_bytes = resp.read()
    data = json.loads(body_bytes.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("API response is not a JSON array")
    return data


def _get_pr_files(repo: str, pr_number: int, token: str) -> list:
    """Paginate _get_pr_files_page until a short page is returned.
    Hard ceiling at MAX_FILES -> fail-closed."""
    files: list = []
    page = 1
    while True:
        try:
            page_rows = _get_pr_files_page(repo, pr_number, page, token)
        except urllib.error.HTTPError as e:
            _fail(f"GitHub API returned HTTP {e.code} on page {page}: {e.reason}")
        except urllib.error.URLError as e:
            _fail(f"GitHub API unreachable on page {page}: {e}")
        except json.JSONDecodeError as e:
            _fail(f"GitHub API page {page} returned malformed JSON: {e}")
        except ValueError as e:
            _fail(f"GitHub API page {page} schema invalid: {e}")
        except Exception as e:
            _fail(f"GitHub API call failed on page {page}: {e!r}")

        if not isinstance(page_rows, list):
            _fail(f"GitHub API page {page} did not return a JSON array")

        for entry in page_rows:
            if not isinstance(entry, dict):
                _fail(f"GitHub API page {page} contains non-dict entry")
            fn = entry.get("filename")
            if not isinstance(fn, str) or not fn:
                _fail(f"GitHub API page {page} contains invalid filename")
            files.append(fn)

        # GitHub PR-files API exposes at most 3000 changed files; reaching that count
        # means we cannot prove completeness, so fail-closed with a precise message.
        if len(files) >= MAX_FILES:
            _fail(f"3000-file API ceiling reached; completeness cannot be proven")

        if len(page_rows) < PAGE_SIZE:
            break  # last page
        page += 1

    if not files:
        _fail("GitHub API returned no files for the PR (unexpected)")

    # deterministic dedupe (preserve first-seen order)
    seen: set = set()
    deduped: list = []
    for f in files:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


# ---------- body parsing ----------

def _parse_metadata(body: str) -> dict:
    """Returns {field: {'value': str, 'count': int}} per known field.
    'count' is the number of times the field line appeared (used for duplicate
    detection). Body is DATA only; never executed."""
    out: dict = {}
    for key in _FIELDS:
        pattern = rf"(?m)^\s*{re.escape(key)}\s*:\s*(.*?)\s*$"
        matches = re.findall(pattern, body)
        out[key] = {"value": matches[0].strip() if matches else "", "count": len(matches)}
    return out


def _parse_categories_list(s: str) -> list:
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _is_placeholder(s: str) -> bool:
    """Reject obvious placeholder text. Two checks:
    1) whole field (after strip+lower) equals a known placeholder token
    2) any whitespace-separated token in the field equals a known placeholder token
    This catches both 'TBD' as a body and 'this is just tbd filler text'.
    """
    lowered = s.strip().lower()
    if not lowered or lowered in INVALID_FILLER:
        return True
    tokens = re.findall(r"\S+", lowered)
    return any(tok in INVALID_FILLER for tok in tokens)


def _count_non_whitespace(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


# ---------- main ----------

def main() -> int:
    repo_root = os.getcwd()
    # minimal arg parsing: support --repo-root PATH for tests
    args = sys.argv[1:]
    if "--repo-root" in args:
        i = args.index("--repo-root")
        if i + 1 < len(args):
            repo_root = args[i + 1]

    _check_mock_safety()
    manifest = _load_manifest(repo_root)

    # 1) determine changed files (mock or live)
    mock_files = os.environ.get("GOVERNANCE_MOCK_FILES", "").strip()
    if mock_files:
        changed = [x.strip() for x in mock_files.split(",") if x.strip()]
        if not changed:
            _fail("GOVERNANCE_MOCK_FILES is set but empty")
        ev_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
        body = (_read_body_from_event(ev_path) if ev_path
                else os.environ.get("GOVERNANCE_MOCK_BODY", ""))
    else:
        ev_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        if not ev_path:
            _fail("GITHUB_EVENT_PATH not set")
        if not token:
            _fail("GITHUB_TOKEN not set")
        if not repo:
            _fail("GITHUB_REPOSITORY not set")
        pr = _read_event(ev_path)
        pr_number = pr.get("number")
        if not isinstance(pr_number, int):
            _fail("event.pull_request.number missing or not an int")
        changed = _get_pr_files(repo, pr_number, token)
        body = _read_body_from_event(ev_path)

    # 2) detect
    hits = _detect(manifest, changed)

    # 3) no high-risk -> PASS
    if not hits:
        _info(f"PASS: no high-risk paths in PR diff ({len(changed)} file(s) checked)")
        return 0

    # 4) high-risk present -> require metadata
    _info("HIGH-RISK paths detected in PR diff:")
    for cat in sorted(hits):
        for f in hits[cat]:
            _info(f"  - {cat}: {f}")

    metadata = _parse_metadata(body)
    cats_meta = metadata["Governance-Categories"]
    just_meta = metadata["Governance-Justification"]
    val_meta = metadata["Governance-Validation"]

    errors: list = []

    # duplicate fields
    if cats_meta["count"] != 1:
        errors.append(f"Governance-Categories appears {cats_meta['count']} times (must be exactly 1)")
    if just_meta["count"] != 1:
        errors.append(f"Governance-Justification appears {just_meta['count']} times (must be exactly 1)")
    if val_meta["count"] != 1:
        errors.append(f"Governance-Validation appears {val_meta['count']} times (must be exactly 1)")

    cats_field = cats_meta["value"]
    just_field = just_meta["value"]
    val_field = val_meta["value"]

    if not cats_field:
        errors.append("missing 'Governance-Categories:'")
    if not just_field:
        errors.append("missing 'Governance-Justification:'")
    if not val_field:
        errors.append("missing 'Governance-Validation:'")

    if just_field and _is_placeholder(just_field):
        errors.append(f"Governance-Justification is placeholder ({just_field!r})")
    if val_field and _is_placeholder(val_field):
        errors.append(f"Governance-Validation is placeholder ({val_field!r})")

    if just_field and _count_non_whitespace(just_field) < MIN_JUSTIFICATION_CHARS:
        errors.append(f"Governance-Justification has <{MIN_JUSTIFICATION_CHARS} non-whitespace chars "
                      f"({_count_non_whitespace(just_field)})")
    if val_field and _count_non_whitespace(val_field) < MIN_JUSTIFICATION_CHARS:
        errors.append(f"Governance-Validation has <{MIN_JUSTIFICATION_CHARS} non-whitespace chars "
                      f"({_count_non_whitespace(val_field)})")

    declared: list = []
    detected = set(hits.keys())
    if cats_field:
        declared = _parse_categories_list(cats_field)
        if declared:
            # duplicate categories
            seen: set = set()
            dups: list = []
            for c in declared:
                if c in seen and c not in dups:
                    dups.append(c)
                seen.add(c)
            if dups:
                errors.append(f"duplicate categories in declaration: {dups}")
            # unknown
            unknown = [c for c in declared if c not in KNOWN_CATEGORIES]
            if unknown:
                errors.append(f"unknown categories declared: {unknown}")
            # coverage
            decl_set = set(declared)
            missing = detected - decl_set
            if missing:
                errors.append(f"declared categories do not cover detected ones: missing {sorted(missing)}")
            extra = decl_set - detected
            if extra:
                _info(f"note: declared extra categories not in PR diff: {sorted(extra)}")

    if errors:
        _fail("; ".join(errors))
        return 1  # unreachable, _fail exits

    _info(f"PASS: governance metadata covers {len(detected)} detected categories "
          f"({', '.join(sorted(detected))})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # pragma: no cover
        _fail(f"unexpected error: {e!r}")
