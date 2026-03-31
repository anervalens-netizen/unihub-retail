import asyncio
from pathlib import Path
import pandas as pd
from db.connection import get_pool

async def export_agents():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT
                ram.agent,
                ram.site_code,
                ram.locatie,
                ram.firma,
                ram.regional,
                ram.asm,
                ram.import_month
            FROM reporting_agent_month ram
            ORDER BY ram.agent, ram.import_month DESC
        """)
        df = pd.DataFrame([dict(r) for r in rows])
        output_path = Path.cwd() / "agents_export.xlsx"
        df.to_excel(output_path, index=False, engine="openpyxl")
        print(f"Exported {len(df)} rows to {output_path}")
        print(df.head(10).to_string())

if __name__ == "__main__":
    asyncio.run(export_agents())
