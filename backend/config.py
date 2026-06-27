"""Central config validation — fail-fast la startup pe env vars critice.

Authentik OIDC/JWKS RS256 este singurul mecanism de autentificare. Nu exista
secret JWT local de validat.

Check-uri:
- DATABASE_URL prezent, format minimal valid
- VISITS_DB_PATH fișier existent (doar în producție)
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISITS_DB_PATH = _REPO_ROOT / "data" / "visits" / "visits.db"
DEFAULT_VISITS_IMAGES_DIR = _REPO_ROOT / "data" / "visits" / "images"


class ConfigError(RuntimeError):
    """Ridicat la boot când env vars critice sunt invalide sau lipsă."""


def _is_production() -> bool:
    return os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"


def get_visits_db_path() -> Path:
    return Path(os.getenv("VISITS_DB_PATH", str(DEFAULT_VISITS_DB_PATH))).expanduser()


def get_visits_images_dir() -> Path:
    return Path(os.getenv("VISITS_IMAGES_DIR", str(DEFAULT_VISITS_IMAGES_DIR))).expanduser()


def validate_required_env_vars() -> None:
    """Validează env vars critice. Ridică ConfigError dacă ceva e greșit.

    Se apelează cât mai devreme în lifespan — înainte de init_db_pool,
    înainte de bootstrap. Dacă rupem ceva aici, backend-ul refuză să pornească
    și systemd loghează eroarea clar.
    """
    errors: list[str] = []

    # DATABASE_URL
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        errors.append("DATABASE_URL este gol sau nesetat")
    elif not db_url.startswith(("postgresql://", "postgres://")):
        errors.append(
            f"DATABASE_URL are schemă invalidă (găsit: {db_url[:20]}...); "
            "trebuie să înceapă cu postgresql:// sau postgres://"
        )

    # VISITS_DB_PATH — strict doar în producție
    if _is_production():
        visits_path_raw = os.getenv("VISITS_DB_PATH", "").strip()
        if not visits_path_raw:
            errors.append("VISITS_DB_PATH nesetat (obligatoriu în producție)")
        elif not get_visits_db_path().is_file():
            errors.append(
                f"VISITS_DB_PATH={visits_path_raw} nu există sau nu e fișier "
                "(obligatoriu în producție; Vizite + Management depind de el)"
            )

    if errors:
        raise ConfigError(
            "Config invalid la startup:\n  - " + "\n  - ".join(errors)
        )
