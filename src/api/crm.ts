import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { StoreScore } from './generated/runtime-types';

export async function fetchScores(month: string): Promise<StoreScore[]> {
  const params: RetailOperationQueries['get_scores_api_crm_scores_get'] = { month };
  return generatedGet('get_scores_api_crm_scores_get', { params });
}
