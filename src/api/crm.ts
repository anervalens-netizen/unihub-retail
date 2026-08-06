import { generatedGet } from './generated/client';
import type { StoreScore } from './generated/runtime-types';

export async function fetchScores(month: string): Promise<StoreScore[]> {
  return await generatedGet('get_scores_api_crm_scores_get', { params: { month } }) as StoreScore[];
}
