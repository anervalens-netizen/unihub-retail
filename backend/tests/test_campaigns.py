"""Unit tests for campaigns models."""
from __future__ import annotations

import pytest
from models import IncentiveTopAgent, PromoTopStore


def test_incentive_top_agent_full_fields():
    agent = IncentiveTopAgent(
        agent_name="POPESCU ION",
        qty_sold=150,
        val_incentive=750.0,
        achievement=1.03,
    )
    assert agent.agent_name == "POPESCU ION"
    assert agent.qty_sold == 150
    assert agent.val_incentive == 750.0
    assert agent.achievement == pytest.approx(1.03)


def test_incentive_top_agent_no_target():
    agent = IncentiveTopAgent(
        agent_name="IONESCU ANA",
        qty_sold=80,
        val_incentive=0.0,
        achievement=None,
    )
    assert agent.achievement is None


def test_promo_top_store_has_firma():
    store = PromoTopStore(
        store_name="S001 - Pitesti Park Lake",
        qty=200,
        total_qty=200,
        category_qty=0,
        incentive_value=1000.0,
        achievement=1.05,
        firma="Mobiup",
    )
    assert store.firma == "Mobiup"


def test_promo_top_store_firma_default_empty():
    store = PromoTopStore(
        store_name="S002 - Ploiesti",
        qty=100,
        total_qty=100,
        category_qty=0,
    )
    assert store.firma == ""
