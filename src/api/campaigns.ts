import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { CampaignSnapshot, CampaignsPromotionsResponse, FocusHistoryResponse } from './generated/runtime-types';

export type CampaignQuery = RetailOperationQueries['get_campaign_overview_api_campaigns_overview_get'];
export type CampaignPromotionsQuery = RetailOperationQueries['get_promotions_incentives_api_campaigns_promotions_incentives_get'];

export async function getCampaignSnapshot(query: CampaignQuery, signal?: AbortSignal): Promise<CampaignSnapshot> {
  return generatedGet('get_campaign_overview_api_campaigns_overview_get', { params: query, signal });
}

export async function getFocusHistory(
  query: RetailOperationQueries['get_focus_history_api_campaigns_history_get'],
  signal?: AbortSignal,
): Promise<FocusHistoryResponse> {
  return generatedGet('get_focus_history_api_campaigns_history_get', { params: query, signal });
}

export async function getPromotionsIncentives(
  query: CampaignPromotionsQuery,
  signal?: AbortSignal,
): Promise<CampaignsPromotionsResponse> {
  return await generatedGet('get_promotions_incentives_api_campaigns_promotions_incentives_get', {
    params: query,
    signal,
  });
}

export type { CampaignSnapshot, CampaignsPromotionsResponse, FocusHistoryResponse };
