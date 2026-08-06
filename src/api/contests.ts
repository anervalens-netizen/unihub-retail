import { generatedGet } from './generated/client';
import type { ContestResponse } from './types';

/**
 * Concursul activ pentru luna data (sau null daca nu exista).
 * Leaderboard-ul e scoped server-side la zona din config (ex. asm=Andrei Stancu),
 * deci nu trimite filtrele globale ale aplicatiei.
 */
export async function getActiveContest(month: string): Promise<ContestResponse | null> {
  return await generatedGet('get_active_contest_api_contests_active_get', { params: { month } }) as ContestResponse | null;
}

export async function getActiveContests(month: string, signal?: AbortSignal): Promise<ContestResponse[]> {
  return await generatedGet('get_active_contests_api_contests_active_all_get', { params: { month }, signal }) as ContestResponse[];
}
