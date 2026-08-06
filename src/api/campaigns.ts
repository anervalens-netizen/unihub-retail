import { generatedGet } from './generated/client';
import type { CampaignSnapshot, CampaignsPromotionsResponse, FocusHistoryResponse } from './types';

export interface CampaignQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
}

export async function getCampaignSnapshot(query: CampaignQuery, signal?: AbortSignal): Promise<CampaignSnapshot> {
  return generatedGet('get_campaign_overview_api_campaigns_overview_get', { params: query, signal }) as unknown as CampaignSnapshot;
}

export async function getFocusHistory(
  query: CampaignQuery & { months_back?: number },
  signal?: AbortSignal,
): Promise<FocusHistoryResponse> {
  return generatedGet('get_focus_history_api_campaigns_history_get', { params: query, signal }) as unknown as FocusHistoryResponse;
}

export async function getPromotionsIncentives(
  startDate: string,
  endDate: string,
  filters?: {
    firma?: string;
    regional?: string;
    asm?: string;
    site_code?: string;
    agent?: string;
    promotion_key?: string;
    view?: 'all' | 'promo' | 'incentive';
    current_scope?: boolean;
    include_closed_stores?: boolean;
  },
  signal?: AbortSignal,
): Promise<CampaignsPromotionsResponse> {
  return generatedGet('get_promotions_incentives_api_campaigns_promotions_incentives_get', {
    params: {
      start_date: startDate,
      end_date: endDate,
      ...(filters?.firma && { firma: filters.firma }),
      ...(filters?.regional && { regional: filters.regional }),
      ...(filters?.asm && { asm: filters.asm }),
      ...(filters?.site_code && { site_code: filters.site_code }),
      ...(filters?.agent && { agent: filters.agent }),
      ...(filters?.promotion_key && { promotion_key: filters.promotion_key }),
      ...(filters?.view && { view: filters.view }),
      ...(filters?.current_scope !== undefined && { current_scope: filters.current_scope }),
      ...(filters?.include_closed_stores !== undefined && { include_closed_stores: filters.include_closed_stores }),
    },
    signal,
  }) as unknown as CampaignsPromotionsResponse;
}
