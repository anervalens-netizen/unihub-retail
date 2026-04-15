from __future__ import annotations

from collections.abc import Iterable
import os
from typing import Any

from services.auth_service import hash_password, verify_password

TL_DEFAULT_PASSWORD = os.getenv("TL_DEFAULT_PASSWORD", "9999")

TL_ACCOUNTS = {
    "andreea.ciobanu": {
        "full_name": "Andreea Ciobanu",
        "site_codes": [
            "CRFFEER",
            "MCRFBAL",
            "PROM",
            "AUCHMIL2",
            "CRFORH1",
            "MEGAMALL",
            "PROMEN",
            "AUCHMILI",
            "CORPANTE",
            "MC-MEGAMALL",
        ],
    },
    "andreea.plingu": {
        "full_name": "Andreea Plingu",
        "site_codes": [
            "CTAUCH",
            "CTCITYPRK",
            "CTCRFTOM",
            "CCTCIT",
            "CTCORA",
            "CTVIVO",
        ],
    },
    "laurentiu.cernat": {
        "full_name": "Laurentiu Cernat",
        "site_codes": [
            "COTROCENI",
            "CRFVUL",
            "PRKLK",
            "SUNPLZ",
            "UNIRII",
            "AFICOTRO",
            "AUCHTRIC",
            "CORALEX",
            "CORLUJER",
            "CRFARENA",
        ],
    },
}


def get_default_core_credentials() -> dict[str, tuple[str, str, str]]:
    return {
        "admin": (
            os.getenv("DEFAULT_ADMIN_USERNAME", "admin"),
            os.getenv("DEFAULT_ADMIN_PASSWORD", "9999"),
            "Administrator UniHub",
        ),
        "management": (
            os.getenv("DEFAULT_MANAGEMENT_USERNAME", "management"),
            os.getenv("DEFAULT_MANAGEMENT_PASSWORD", "9999"),
            "Management UniHub",
        ),
    }


async def ensure_core_users(conn) -> None:
    credentials = get_default_core_credentials()
    for role, (username, password, full_name) in credentials.items():
        await conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (username) DO NOTHING
            """,
            username,
            hash_password(password),
            full_name,
            role,
        )


async def get_core_user_bootstrap_status(conn) -> list[dict[str, Any]]:
    credentials = get_default_core_credentials()
    rows = await conn.fetch(
        """
        SELECT username, role, is_active
        FROM users
        WHERE lower(username) = ANY($1::text[])
        ORDER BY role ASC
        """,
        [username.lower() for username, _, _ in credentials.values()],
    )
    existing = {str(row["username"]).lower(): dict(row) for row in rows}
    status_rows: list[dict[str, Any]] = []
    for role, (username, _, _) in credentials.items():
        row = existing.get(username.lower())
        status_rows.append(
            {
                "role": role,
                "username": username,
                "exists": row is not None,
                "is_active": bool(row["is_active"]) if row is not None else False,
            }
        )
    return status_rows


async def reset_default_core_users(conn) -> list[dict[str, str]]:
    credentials = get_default_core_credentials()
    reset_users: list[dict[str, str]] = []
    for role, (username, password, full_name) in credentials.items():
        await conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES ($1, $2, $3, $4, true)
            ON CONFLICT (username) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                full_name = EXCLUDED.full_name,
                role = EXCLUDED.role,
                is_active = true
            """,
            username,
            hash_password(password),
            full_name,
            role,
        )
        reset_users.append({"role": role, "username": username, "password": password})
    return reset_users


async def ensure_tl_users_and_assignments(conn) -> None:
    await ensure_tl_users(conn)

    tl_user_rows = await conn.fetch(
        """
        SELECT id, username
        FROM users
        WHERE username = ANY($1::text[])
        """,
        list(TL_ACCOUNTS.keys()),
    )
    username_to_id = {row["username"]: row["id"] for row in tl_user_rows}

    for username, config in TL_ACCOUNTS.items():
        user_id = username_to_id.get(username)
        if user_id is None:
            continue
        await conn.execute("DELETE FROM tl_store_assignments WHERE user_id = $1", user_id)
        await conn.executemany(
            """
            INSERT INTO tl_store_assignments (user_id, site_code)
            SELECT $1, $2
            WHERE EXISTS (SELECT 1 FROM stores WHERE site_code = $2)
            ON CONFLICT (user_id, site_code) DO NOTHING
            """,
            [(user_id, site_code) for site_code in config["site_codes"]],
        )


async def ensure_tl_users(conn) -> None:
    for username, config in TL_ACCOUNTS.items():
        await conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES ($1, $2, $3, 'tl')
            ON CONFLICT (username) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                role = 'tl',
                is_active = true
            """,
            username,
            hash_password(TL_DEFAULT_PASSWORD),
            config["full_name"],
        )


def should_sync_tl_assignments_on_boot() -> bool:
    return os.getenv("SYNC_TL_ASSIGNMENTS_ON_BOOT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def should_reset_default_users_on_boot() -> bool:
    return os.getenv("RESET_DEFAULT_USERS_ON_BOOT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_unihub_env() -> str:
    return os.getenv("UNIHUB_ENV", "development").strip().lower()


def is_production_env() -> bool:
    return get_unihub_env() == "production"


async def assert_no_default_passwords_in_production(conn) -> None:
    """Fail-fast la boot dacă admin/management au încă parola default în producție.

    Parola default `9999` e folosită în dev + la bootstrap inițial. În producție,
    e o gaură de securitate critică: oricine cu acces la endpoint /auth/login
    poate intra ca admin. Check-ul compară hash-ul stocat în DB cu un hash
    default — dacă verify trece, parola nu a fost schimbată.
    """
    if not is_production_env():
        return

    credentials = get_default_core_credentials()
    offenders: list[str] = []
    for role, (username, default_password, _) in credentials.items():
        row = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE username = $1",
            username,
        )
        if row is None:
            continue
        stored_hash = row["password_hash"]
        if not stored_hash:
            continue
        try:
            if verify_password(default_password, stored_hash):
                offenders.append(f"{role}/{username}")
        except Exception:
            # hash corrupt / format necunoscut → nu blocăm, doar sărim
            continue

    if offenders:
        allow_default = os.getenv("UNIHUB_ALLOW_DEFAULT_PASSWORDS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        message = (
            "SECURITY: conturile core au încă parola default în producție: "
            + ", ".join(offenders)
        )
        if allow_default:
            # escape hatch pentru bootstrap inițial în prod — loghează, nu blochează
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "%s. UNIHUB_ALLOW_DEFAULT_PASSWORDS=1 active — skip fail-fast. "
                "Schimbă parolele și dezactivează flag-ul ASAP.",
                message,
            )
            return
        raise RuntimeError(
            message
            + ". Schimbă parolele via UI sau SQL, apoi restart. "
            + "Pentru bootstrap inițial, setează UNIHUB_ALLOW_DEFAULT_PASSWORDS=1 (o singură dată)."
        )


def get_tl_usernames() -> Iterable[str]:
    return TL_ACCOUNTS.keys()
