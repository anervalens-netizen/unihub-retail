#!/usr/bin/env python3
"""Fail closed when editable Python requirements and generated locks disagree."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\\\s]+)\s*\\?$")


def load_source(path: Path) -> dict[str, Requirement]:
    requirements: dict[str, Requirement] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            raise SystemExit(f"{path}:{line_number}: nested requirement directives are not supported by this authority")
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            raise SystemExit(f"{path}:{line_number}: invalid requirement: {exc}") from exc
        if requirement.url is not None:
            raise SystemExit(f"{path}:{line_number}: direct URL requirements are not supported by this authority")
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        name = str(canonicalize_name(requirement.name))
        if name in requirements:
            raise SystemExit(f"{path}:{line_number}: duplicate direct requirement for {name}")
        requirements[name] = requirement
    return requirements


def load_lock(path: Path) -> dict[str, Version]:
    pins: dict[str, Version] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = PIN_RE.match(raw.strip())
        if match is None:
            continue
        name = str(canonicalize_name(match.group(1)))
        try:
            version = Version(match.group(2))
        except InvalidVersion as exc:
            raise SystemExit(f"{path}:{line_number}: invalid pinned version for {name}: {match.group(2)}") from exc
        previous = pins.get(name)
        if previous is not None and previous != version:
            raise SystemExit(f"{path}:{line_number}: conflicting pins for {name}: {previous} vs {version}")
        pins[name] = version
    return pins


def verify(source_rel: str, lock_rel: str) -> None:
    source_path = ROOT / source_rel
    lock_path = ROOT / lock_rel
    source = load_source(source_path)
    pins = load_lock(lock_path)
    for name, requirement in sorted(source.items()):
        version = pins.get(name)
        if version is None:
            raise SystemExit(f"{lock_rel}: missing direct requirement {name} declared by {source_rel}")
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
            raise SystemExit(
                f"{lock_rel}: {name}=={version} does not satisfy {source_rel} declaration {requirement}"
            )


def main() -> None:
    # The dev lock is compiled from both editable sources; the runtime lock is
    # compiled from requirements.txt only. Verify direct semantic coherence in
    # every supported source/lock relationship.
    verify("backend/requirements.txt", "backend/requirements.lock")
    verify("backend/requirements.txt", "backend/requirements-dev.lock")
    verify("backend/requirements-dev.txt", "backend/requirements-dev.lock")
    print("Python requirement locks are semantically coherent")


if __name__ == "__main__":
    main()
