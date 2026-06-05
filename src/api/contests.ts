import { client } from './client';
import type { ContestResponse } from './types';

/**
 * Concursul activ pentru luna data (sau null daca nu exista).
 * Leaderboard-ul e scoped server-side la zona din config (ex. asm=Andrei Stancu),
 * deci nu trimite filtrele globale ale aplicatiei.
 */
export async function getActiveContest(month: string): Promise<ContestResponse | null> {
  const { data } = await client.get<ContestResponse | null>('/api/contests/active', {
    params: { month },
  });
  return data ?? null;
}

export async function getActiveContests(month: string): Promise<ContestResponse[]> {
  const { data } = await client.get<ContestResponse[]>('/api/contests/active/all', {
    params: { month },
  });
  return data ?? [];
}
