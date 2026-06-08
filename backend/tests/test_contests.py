"""Tests for contest config parsing + leaderboard scoring."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.contests_config import (
    ContestDefinition,
    get_active_contest,
    get_active_contests,
    parse_contests,
)
from services.contests import ContestsService
from services.promo_copurchase import PromoCoPurchaseResult


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


# ----------------------------- config parsing -----------------------------

class TestContestConfigParsing:
    def _raw(self):
        return {
            "contests": [
                {
                    "key": "iunie-2026-stancu",
                    "title": "Concurs Iunie",
                    "subtitle": "sub",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "scope": {"asm": "Andrei Stancu"},
                    "rules": [
                        {"type": "focus", "points": 1, "label": "Focus"},
                        {"type": "promo", "points": 1, "label": "Promo"},
                        {"type": "price_above", "points": 1, "threshold": 150, "label": ">150"},
                    ],
                    "prizes": [
                        {"rank_from": 1, "rank_to": 1, "label": "M7 Plus"},
                        {"rank_from": 2, "rank_to": 3, "label": "BoomX"},
                        {"rank_from": 4, "rank_to": 6, "label": "Macaron"},
                    ],
                }
            ]
        }

    def test_parse_full_contest(self):
        contests = parse_contests(self._raw())
        assert len(contests) == 1
        c = contests[0]
        assert c.key == "iunie-2026-stancu"
        assert c.scope == {"asm": "Andrei Stancu"}
        assert len(c.rules) == 3
        price = next(r for r in c.rules if r.type == "price_above")
        assert price.threshold == 150.0
        assert len(c.prizes) == 3

    def test_prize_for_rank(self):
        c = parse_contests(self._raw())[0]
        assert c.prize_for_rank(1) == "M7 Plus"
        assert c.prize_for_rank(2) == "BoomX"
        assert c.prize_for_rank(3) == "BoomX"
        assert c.prize_for_rank(5) == "Macaron"
        assert c.prize_for_rank(7) is None

    def test_invalid_rule_type_skipped(self):
        raw = self._raw()
        raw["contests"][0]["rules"].append({"type": "bogus", "points": 5})
        c = parse_contests(raw)[0]
        assert all(r.type in {"focus", "promo", "price_above"} for r in c.rules)
        assert len(c.rules) == 3

    def test_price_rule_without_threshold_skipped(self):
        raw = self._raw()
        raw["contests"][0]["rules"] = [{"type": "price_above", "points": 1}]
        c = parse_contests(raw)[0]
        assert c.rules == []

    def test_missing_key_skips_contest(self):
        raw = {"contests": [{"title": "x", "start_date": "2026-06-01", "end_date": "2026-06-30"}]}
        assert parse_contests(raw) == []

    def test_get_active_contest_overlaps_month(self):
        with patch("services.contests_config.load_contests_config", return_value=(self._raw(), None)):
            c, err = get_active_contest("2026-06")
            assert err is None
            assert c is not None and c.key == "iunie-2026-stancu"

    def test_get_active_contests_returns_all_overlaps(self):
        raw = self._raw()
        second = dict(raw["contests"][0])
        second["key"] = "iunie-2026-condorateanu"
        second["scope"] = {"asm": "Mihai Condorateanu"}
        second["prizes"] = [
            {"rank_from": 1, "rank_to": 1, "label": "BoomX"},
            {"rank_from": 2, "rank_to": 3, "label": "Macaron"},
        ]
        raw["contests"].append(second)
        with patch("services.contests_config.load_contests_config", return_value=(raw, None)):
            contests, err = get_active_contests("2026-06")
            assert err is None
            assert [c.key for c in contests] == [
                "iunie-2026-stancu",
                "iunie-2026-condorateanu",
            ]
            assert contests[1].scope == {"asm": "Mihai Condorateanu"}

    def test_get_active_contest_other_month_none(self):
        with patch("services.contests_config.load_contests_config", return_value=(self._raw(), None)):
            c, err = get_active_contest("2026-08")
            assert c is None and err is None


# ----------------------------- scoring service -----------------------------

def _contest_def():
    from services.contests_config import ContestPrize, ContestRule
    return ContestDefinition(
        key="iunie-2026-stancu",
        title="Concurs Iunie",
        subtitle="sub",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        scope={"asm": "Andrei Stancu"},
        rules=[
            ContestRule(type="focus", points=1, label="Focus"),
            ContestRule(type="promo", points=1, label="Promo"),
            ContestRule(type="price_above", points=1, label=">150", threshold=150.0),
        ],
        prizes=[
            ContestPrize(rank_from=1, rank_to=1, label="M7 Plus"),
            ContestPrize(rank_from=2, rank_to=3, label="BoomX"),
            ContestPrize(rank_from=4, rank_to=6, label="Macaron"),
        ],
    )


def _contest_def_mihai():
    from services.contests_config import ContestPrize, ContestRule
    return ContestDefinition(
        key="iunie-2026-condorateanu",
        title="Concurs Iunie",
        subtitle="sub",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        scope={"asm": "Mihai Condorateanu"},
        rules=[
            ContestRule(type="focus", points=1, label="Focus"),
            ContestRule(type="promo", points=1, label="Promo"),
            ContestRule(type="price_above", points=1, label=">150", threshold=150.0),
        ],
        prizes=[
            ContestPrize(rank_from=1, rank_to=1, label="BoomX"),
            ContestPrize(rank_from=2, rank_to=3, label="Macaron"),
        ],
    )


def _service():
    repo = MagicMock()
    repo.fetch_agent_scores = AsyncMock(return_value=[
        FakeRow(agent="Agent1", site_code="S1", store_name="Store 1", firma="Mobiup", focus_units=5, price_units=3),
        FakeRow(agent="Agent2", site_code="S2", store_name="Store 2", firma="MobiCell", focus_units=2, price_units=2),
        FakeRow(agent="Agent3", site_code="S3", store_name="Store 3", firma="Mobiup", focus_units=0, price_units=0),
    ])
    repo.fetch_scope_store_count = AsyncMock(return_value=23)
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return ContestsService(repo, pool)


class TestContestScoring:
    @pytest.mark.asyncio
    @patch("services.contests.compute_promo_copurchase", new_callable=AsyncMock)
    @patch("services.contests.parse_promotion_definition")
    @patch("services.contests.load_special_cards_config", return_value=({}, None))
    @patch("services.contests.get_active_contest")
    async def test_leaderboard_points_rank_prizes(
        self, mock_active, mock_cfg, mock_promo_def, mock_cp
    ):
        svc = _service()
        mock_active.return_value = (_contest_def(), None)
        mock_promo_def.return_value = (
            {"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 30), "item_codes": ["CL1"]},
            None,
        )
        mock_cp.return_value = PromoCoPurchaseResult(
            excluded_units={
                ("S1", "Agent1", "CL1"): 2,  # Agent1 -> 2 bonuri promo
                ("S1", "Agent2", "CL2"): 1,  # Agent2 -> 1 bon promo
            }
        )
        resp = await svc.get_active_contest("2026-06")
        assert resp is not None
        assert resp.store_count == 23
        assert len(resp.leaderboard) == 2  # Agent3 (0 puncte) exclus

        a1 = resp.leaderboard[0]
        # focus 5 + promo 2 + price 3 = 10
        assert a1.agent == "Agent1"
        assert a1.store_name == "Store 1"
        assert a1.firma == "Mobiup"
        assert a1.rank == 1
        assert a1.focus_points == 5 and a1.promo_points == 2 and a1.price_points == 3
        assert a1.total_points == 10
        assert a1.prize == "M7 Plus"

        a2 = resp.leaderboard[1]
        # focus 2 + promo 1 + price 2 = 5
        assert a2.agent == "Agent2"
        assert a2.rank == 2
        assert a2.total_points == 5
        assert a2.prize == "BoomX"

    @pytest.mark.asyncio
    @patch("services.contests.get_active_contest", return_value=(None, None))
    async def test_no_active_contest_returns_none(self, mock_active):
        svc = _service()
        assert await svc.get_active_contest("2026-08") is None

    @pytest.mark.asyncio
    @patch("services.contests.compute_promo_copurchase", new_callable=AsyncMock)
    @patch("services.contests.parse_promotion_definition", return_value=(None, None))
    @patch("services.contests.load_special_cards_config", return_value=({}, None))
    @patch("services.contests.get_active_contests")
    async def test_get_active_contests_builds_all_active_configs(
        self, mock_active, mock_cfg, mock_promo_def, mock_cp
    ):
        svc = _service()
        mock_active.return_value = ([_contest_def(), _contest_def_mihai()], None)
        responses = await svc.get_active_contests("2026-06")
        assert [resp.key for resp in responses] == [
            "iunie-2026-stancu",
            "iunie-2026-condorateanu",
        ]
        assert responses[0].leaderboard[0].prize == "M7 Plus"
        assert responses[1].leaderboard[0].prize == "BoomX"
        mock_cp.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.contests.compute_promo_copurchase", new_callable=AsyncMock)
    @patch("services.contests.parse_promotion_definition", return_value=(None, None))
    @patch("services.contests.load_special_cards_config", return_value=({}, None))
    @patch("services.contests.get_active_contest")
    async def test_no_active_promo_means_zero_promo_points(
        self, mock_active, mock_cfg, mock_promo_def, mock_cp
    ):
        svc = _service()
        mock_active.return_value = (_contest_def(), None)
        resp = await svc.get_active_contest("2026-06")
        assert resp is not None
        # compute_promo_copurchase nu trebuie apelat daca nu exista promo activ
        mock_cp.assert_not_called()
        a1 = resp.leaderboard[0]
        assert a1.promo_points == 0
        # Agent1: focus 5 + price 3 = 8
        assert a1.total_points == 8
