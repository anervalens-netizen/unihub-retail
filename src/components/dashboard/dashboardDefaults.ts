import type { PromoIncentiveSummary } from '../../api/types';

export const DEFAULT_PROMO_INCENTIVE: PromoIncentiveSummary = {
  promo_qty: 0,
  promo_sales: 0,
  promo_impact: 0,
  incentive_qty: 0,
  incentive_value: 0,
  incentive_qualified_stores: 0,
  incentive_qualified_agents: 0,
};

export const DASHBOARD_STALE_MS = 3 * 60 * 1000;
