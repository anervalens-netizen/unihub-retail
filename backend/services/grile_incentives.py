"""Campaign-aware adapter for calendar incentive reads."""
from repositories.grile_incentives import read_incentives as _read_incentives
from services.campaigns.loader import load_campaign_configuration
from services.campaigns.summary import get_store_incentive_multipliers
from services.promotion_evaluation import evaluate_promotion, scope_promotion_definition_to_interval


async def read_incentives(conn, month, calendar, cutoff):
    return await _read_incentives(
        conn, month, calendar, cutoff,
        load_campaign_configuration=load_campaign_configuration,
        get_store_incentive_multipliers=get_store_incentive_multipliers,
        evaluate_promotion=evaluate_promotion,
        scope_promotion_definition_to_interval=scope_promotion_definition_to_interval,
    )
