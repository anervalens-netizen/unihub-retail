from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from db.connection import get_pool
from dependencies import require_role
from models import (
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    FocusProductCreate,
    FocusProductResponse,
    TlAssignmentsUpdate,
)
from services.auth_service import hash_password
from services.reporting_refresh import rebuild_reporting_all

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    user: dict = Depends(require_role("admin")),
) -> list[AdminUserResponse]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role,
                u.is_active,
                COUNT(a.site_code)::int AS assignment_count,
                COALESCE(array_agg(a.site_code ORDER BY a.site_code) FILTER (WHERE a.site_code IS NOT NULL), ARRAY[]::text[]) AS assigned_site_codes
            FROM users u
            LEFT JOIN tl_store_assignments a ON a.user_id = u.id
            GROUP BY u.id, u.username, u.full_name, u.role, u.is_active
            ORDER BY u.role, u.username
            """
        )
    return [AdminUserResponse(**dict(row)) for row in rows]


@router.post(
    "/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: AdminUserCreate, user: dict = Depends(require_role("admin"))
) -> AdminUserResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, username, full_name, role, is_active
            """,
            payload.username.strip(),
            hash_password(payload.password),
            payload.full_name,
            payload.role,
            payload.is_active,
        )
    return AdminUserResponse(**dict(row), assignment_count=0, assigned_site_codes=[])


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: dict = Depends(require_role("admin")),
) -> AdminUserResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există"
            )
        if payload.password:
            await conn.execute(
                """
                UPDATE users
                SET full_name = $2,
                    role = $3,
                    is_active = $4,
                    password_hash = $5
                WHERE id = $1
                """,
                user_id,
                payload.full_name,
                payload.role,
                payload.is_active,
                hash_password(payload.password),
            )
        else:
            await conn.execute(
                """
                UPDATE users
                SET full_name = $2,
                    role = $3,
                    is_active = $4
                WHERE id = $1
                """,
                user_id,
                payload.full_name,
                payload.role,
                payload.is_active,
            )
        row = await conn.fetchrow(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role,
                u.is_active,
                COUNT(a.site_code)::int AS assignment_count,
                COALESCE(array_agg(a.site_code ORDER BY a.site_code) FILTER (WHERE a.site_code IS NOT NULL), ARRAY[]::text[]) AS assigned_site_codes
            FROM users u
            LEFT JOIN tl_store_assignments a ON a.user_id = u.id
            WHERE u.id = $1
            GROUP BY u.id, u.username, u.full_name, u.role, u.is_active
            """,
            user_id,
        )
    return AdminUserResponse(**dict(row))


@router.put("/users/{user_id}/assignments", response_model=AdminUserResponse)
async def update_tl_assignments(
    user_id: int,
    payload: TlAssignmentsUpdate,
    current_user: dict = Depends(require_role("admin")),
) -> AdminUserResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        target_user = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id = $1", user_id
        )
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există"
            )
        if target_user["role"] != "tl":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alocările se aplică doar utilizatorilor TL",
            )

        async with conn.transaction():
            await conn.execute(
                "DELETE FROM tl_store_assignments WHERE user_id = $1", user_id
            )
            if payload.site_codes:
                valid_rows = await conn.fetch(
                    "SELECT site_code FROM stores WHERE site_code = ANY($1::text[])",
                    payload.site_codes,
                )
                valid_site_codes = [row["site_code"] for row in valid_rows]
                await conn.executemany(
                    """
                    INSERT INTO tl_store_assignments (user_id, site_code)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, site_code) DO NOTHING
                    """,
                    [(user_id, site_code) for site_code in valid_site_codes],
                )

        row = await conn.fetchrow(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role,
                u.is_active,
                COUNT(a.site_code)::int AS assignment_count,
                COALESCE(array_agg(a.site_code ORDER BY a.site_code) FILTER (WHERE a.site_code IS NOT NULL), ARRAY[]::text[]) AS assigned_site_codes
            FROM users u
            LEFT JOIN tl_store_assignments a ON a.user_id = u.id
            WHERE u.id = $1
            GROUP BY u.id, u.username, u.full_name, u.role, u.is_active
            """,
            user_id,
        )
    return AdminUserResponse(**dict(row))


@router.get("/focus-products", response_model=list[FocusProductResponse])
async def list_focus_products(
    user: dict = Depends(require_role("admin")),
) -> list[FocusProductResponse]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT item_code, item_name, added_at, added_by
            FROM focus_products
            ORDER BY item_code
            """
        )
    return [FocusProductResponse(**dict(row)) for row in rows]


@router.post(
    "/focus-products",
    response_model=FocusProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_focus_product(
    payload: FocusProductCreate,
    user: dict = Depends(require_role("admin")),
) -> FocusProductResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            item_name = payload.item_name
            if not item_name:
                item_name = await conn.fetchval(
                    """
                    SELECT item_name
                    FROM sales_transactions
                    WHERE item_code = $1
                    ORDER BY import_month DESC, sale_date DESC
                    LIMIT 1
                    """,
                    payload.item_code,
                )
            row = await conn.fetchrow(
                """
                INSERT INTO focus_products (item_code, item_name, added_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (item_code) DO UPDATE
                SET item_name = COALESCE(EXCLUDED.item_name, focus_products.item_name),
                    added_by = EXCLUDED.added_by
                RETURNING item_code, item_name, added_at, added_by
                """,
                payload.item_code.strip(),
                item_name,
                user["id"],
            )
            await rebuild_reporting_all(conn)
    return FocusProductResponse(**dict(row))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int, current_user: dict = Depends(require_role("admin"))
) -> dict[str, bool]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există"
            )
        if user_id == current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nu te poți șterge pe tine însuți",
            )
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)
    return {"deleted": True}


@router.delete("/focus-products/{item_code}")
async def delete_focus_product(
    item_code: str,
    user: dict = Depends(require_role("admin")),
) -> dict[str, bool]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "DELETE FROM focus_products WHERE item_code = $1",
                item_code,
            )
            if result != "DELETE 0":
                await rebuild_reporting_all(conn)
    if result == "DELETE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Produsul focus nu există"
        )
    return {"deleted": True}
