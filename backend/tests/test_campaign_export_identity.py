from datetime import date
from unittest.mock import AsyncMock

import pytest

from repositories.campaigns import CampaignsRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("current_scope,alias", [(False, "agg"), (True, "s")])
async def test_export_rm_uses_the_same_hierarchy_as_campaign_scope(current_scope, alias):
    conn = AsyncMock()
    repo = CampaignsRepository(None)
    scope = dict(firma=None, regional=None, asm=None, site_code=None, agent=None,
                 current_scope=current_scope, include_closed_stores=False)
    await repo.fetch_incentive_store_rows(conn, ["P1"], "2026-08", **scope)
    sql = conn.fetch.call_args.args[0]
    assert f"MAX({alias}.regional) AS regional" in sql
    assert "GROUP BY agg.site_code, agg.item_code, ip.valid_from, ip.valid_to, ip.reward_value" in sql
    await repo.fetch_promo_store_rows(conn, date(2026, 8, 1), date(2026, 8, 31), ["P1"], "2026-08", **scope)
    assert f"MAX({alias}.regional) AS regional" in conn.fetch.call_args.args[0]
