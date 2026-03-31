import { client } from './client';
import type { CampaignSnapshot, CampaignsPromotionsResponse, FocusHistoryResponse } from './types';

export interface CampaignQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
}

export async function getCampaignSnapshot(query: CampaignQuery): Promise<CampaignSnapshot> {
  const { data } = await client.get<CampaignSnapshot>('/api/campaigns/overview', {
    params: query,
  });
  return data;
}

export async function getFocusHistory(
  query: CampaignQuery & { months_back?: number }
): Promise<FocusHistoryResponse> {
  const { data } = await client.get<FocusHistoryResponse>('/api/campaigns/history', {
    params: query,
  });
  return data;
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
  }
): Promise<CampaignsPromotionsResponse> {
  const { data } = await client.get<CampaignsPromotionsResponse>(
    '/api/campaigns/promotions-incentives',
    {
      params: {
        start_date: startDate,
        end_date: endDate,
        ...(filters?.firma && { firma: filters.firma }),
        ...(filters?.regional && { regional: filters.regional }),
        ...(filters?.asm && { asm: filters.asm }),
        ...(filters?.site_code && { site_code: filters.site_code }),
        ...(filters?.agent && { agent: filters.agent }),
      },
    }
  );
  return data;
}
