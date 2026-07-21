import { client } from './client';
import type { FilterOptions } from './types';

export async function getFilterOptions(month: string, signal?: AbortSignal): Promise<FilterOptions> {
  const { data } = await client.get<FilterOptions>('/api/filters/options', { params: { month }, signal });
  return data;
}

export async function getAvailableMonths(): Promise<string[]> {
  const { data } = await client.get<string[]>('/api/filters/months');
  return data;
}
