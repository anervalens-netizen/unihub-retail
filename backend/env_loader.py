"""Canonical dotenv loading for Retail processes and operational scripts.

Real environment variables always win. Files use python-dotenv semantics,
including quoting, comments and interpolation; no Retail process implements an
independent line parser.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: str | Path, *, override: bool = False) -> bool:
    """Load one explicit env file with the repository-wide precedence rule."""
    return bool(load_dotenv(Path(path), override=override))


def load_repository_env(*, override: bool = False) -> bool:
    """Load development `.env`; systemd-injected values remain authoritative."""
    return load_env_file(REPO_ROOT / ".env", override=override)
