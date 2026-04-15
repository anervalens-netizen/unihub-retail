"""Central config validation — fail-fast la startup pe env vars critice.

Motivație: fără validare, env vars lipsă produc erori la prima cerere (500
Internal Server Error) în loc să crape la boot. Backend care pornește curat
dar crapă pe `/api/auth/login` e mai greu de detectat decât unul care
refuză să pornească.

Check-uri:
- DATABASE_URL prezent, format minimal valid
- JWT_SECRET prezent, minim 32 chars (SHA-256 HMAC safety)
- VISITS_DB_PATH fișier existent (doar în producție)
"""
from __future__ import annotations

import os
from pathlib import Path


JWT_SECRET_MIN_LENGTH = 32


class ConfigError(RuntimeError):
    """Ridicat la boot când env vars critice sunt invalide sau lipsă."""


def _is_production() -> bool:
    return os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"


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

    # JWT_SECRET
    jwt_secret = os.getenv("JWT_SECRET", "").strip()
    if not jwt_secret:
        errors.append("JWT_SECRET este gol sau nesetat")
    elif len(jwt_secret) < JWT_SECRET_MIN_LENGTH:
        errors.append(
            f"JWT_SECRET prea scurt: {len(jwt_secret)} chars "
            f"(minim {JWT_SECRET_MIN_LENGTH} — HMAC-SHA256 collision safety)"
        )

    # VISITS_DB_PATH — strict doar în producție
    if _is_production():
        visits_path = os.getenv("VISITS_DB_PATH", "").strip()
        if not visits_path:
            errors.append("VISITS_DB_PATH nesetat (obligatoriu în producție)")
        elif not Path(visits_path).is_file():
            errors.append(
                f"VISITS_DB_PATH={visits_path} nu există sau nu e fișier "
                "(obligatoriu în producție; Vizite + Management depind de el)"
            )

    if errors:
        raise ConfigError(
            "Config invalid la startup:\n  - " + "\n  - ".join(errors)
        )
