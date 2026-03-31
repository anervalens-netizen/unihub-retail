from __future__ import annotations

from collections.abc import Iterable
import os
from typing import Any

from services.auth_service import hash_password

TL_DEFAULT_PASSWORD = "9999"

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


def get_tl_usernames() -> Iterable[str]:
    return TL_ACCOUNTS.keys()
