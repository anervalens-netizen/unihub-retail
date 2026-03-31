import asyncio
import asyncpg


async def fix():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/unihub")
    try:
        await conn.execute(
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"
        )
        await conn.execute(
            "ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'asm', 'management', 'tl'))"
        )
        print("CONSTRAINT UPDATED")
    finally:
        await conn.close()


asyncio.run(fix())
