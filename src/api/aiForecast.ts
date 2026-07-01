import { client } from './client';
import type { AiForecastResponse } from './types';

export interface AiForecastQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
}

export async function getAiForecastCurrent(query: AiForecastQuery): Promise<AiForecastResponse> {
  const { data } = await client.get<AiForecastResponse>('/api/ai-forecast/current', { params: query });
  return data;
}
