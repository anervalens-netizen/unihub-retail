"""Configuration and incentive loading boundary for Campaigns."""

from __future__ import annotations

from typing import Any

from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_promotion_definitions,
)
from services.incentive_db import get_incentive_campaign


def load_campaign_configuration(
    month: str,
    *,
    promotion_key: str | None,
    config_loader=load_special_cards_config,
    definitions_loader=parse_promotion_definitions,
    definition_loader=parse_promotion_definition,
) -> tuple[dict[str, Any], str | None, list[dict[str, Any]], str | None, dict[str, Any] | None, str | None]:
    config, config_error = config_loader()
    definitions, definitions_error = definitions_loader(config, month)
    selected, selected_error = definition_loader(
        config,
        month,
        promotion_key=promotion_key,
    )
    return config, config_error, definitions, definitions_error, selected, selected_error


async def load_incentive_campaign(conn: Any, month: str, loader=get_incentive_campaign) -> dict[str, Any] | None:
    return await loader(conn, month)
