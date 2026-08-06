import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { ContestResponse } from './generated/runtime-types';

/**
 * Concursul activ pentru luna data (sau null daca nu exista).
 * Leaderboard-ul e scoped server-side la zona din config (ex. asm=Andrei Stancu),
 * deci nu trimite filtrele globale ale aplicatiei.
 */
export async function getActiveContest(month: string): Promise<ContestResponse | null> {
  const params: RetailOperationQueries['get_active_contest_api_contests_active_get'] = { month };
  return generatedGet('get_active_contest_api_contests_active_get', { params });
}

export async function getActiveContests(month: string, signal?: AbortSignal): Promise<ContestResponse[]> {
  const params: RetailOperationQueries['get_active_contests_api_contests_active_all_get'] = { month };
  return generatedGet('get_active_contests_api_contests_active_all_get', { params, signal });
}
