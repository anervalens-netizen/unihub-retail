#!/usr/bin/env python3
"""Fail closed when editable Python requirements and generated locks disagree."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PIN_RE = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[([A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+)*)\])?'
    r'==([^\\\s;]+)(?:\s*;\s*(.+?))?\s*\\?$'
)


def canonical_extras(values: set[str] | frozenset[str] | list[str]) -> frozenset[str]:
    return frozenset(str(canonicalize_name(value)) for value in values)


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


def load_lock(path: Path) -> dict[str, tuple[Version, frozenset[str], frozenset[str]]]:
    pins: dict[str, tuple[Version, frozenset[str], frozenset[str]]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = PIN_RE.match(raw.strip())
        if match is None:
            continue
        name = str(canonicalize_name(match.group(1)))
        raw_extras = match.group(2)
        extras = canonical_extras(raw_extras.split(",")) if raw_extras else frozenset()
        try:
            version = Version(match.group(3))
        except InvalidVersion as exc:
            raise SystemExit(f"{path}:{line_number}: invalid pinned version for {name}: {match.group(3)}") from exc
        raw_marker = match.group(4)
        marker_key = ""
        if raw_marker:
            try:
                marker = Marker(raw_marker)
            except InvalidMarker as exc:
                raise SystemExit(f"{path}:{line_number}: invalid environment marker for {name}: {raw_marker}") from exc
            if not marker.evaluate():
                continue
            marker_key = str(marker)
        previous = pins.get(name)
        marker_keys = frozenset({marker_key})
        if previous is not None:
            previous_version, previous_extras, previous_markers = previous
            if previous_version != version:
                raise SystemExit(f"{path}:{line_number}: conflicting pins for {name}: {previous_version} vs {version}")
            extras = previous_extras | extras
            marker_keys = previous_markers | marker_keys
        pins[name] = (version, extras, marker_keys)
    return pins


def verify(source_rel: str, lock_rel: str) -> None:
    source_path = ROOT / source_rel
    lock_path = ROOT / lock_rel
    source = load_source(source_path)
    pins = load_lock(lock_path)
    for name, requirement in sorted(source.items()):
        pin = pins.get(name)
        if pin is None:
            raise SystemExit(f"{lock_rel}: missing direct requirement {name} declared by {source_rel}")
        version, lock_extras, lock_markers = pin
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
            raise SystemExit(
                f"{lock_rel}: {name}=={version} does not satisfy {source_rel} declaration {requirement}"
            )
        missing_extras = canonical_extras(requirement.extras) - lock_extras
        if missing_extras:
            missing = ",".join(sorted(missing_extras))
            raise SystemExit(
                f"{lock_rel}: {name}=={version} is missing requested extras {missing} "
                f"required by {source_rel} declaration {requirement}"
            )
        source_marker = str(requirement.marker) if requirement.marker is not None else ""
        if source_marker not in lock_markers and "" not in lock_markers:
            rendered_source_marker = source_marker or "<none>"
            rendered_lock_markers = ", ".join(sorted(marker or "<none>" for marker in lock_markers))
            raise SystemExit(
                f"{lock_rel}: {name}=={version} marker mismatch for {source_rel}: "
                f"source={rendered_source_marker}; lock={rendered_lock_markers}"
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
