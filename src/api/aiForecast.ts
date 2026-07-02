import { client } from './client';
import type { AiForecastMetric, AiForecastResponse, AiForecastRollingResponse } from './types';

export interface AiForecastQuery {
  month: string;
  metric?: AiForecastMetric;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
}

export async function getAiForecastCurrent(query: AiForecastQuery): Promise<AiForecastResponse> {
  const { data } = await client.get<AiForecastResponse>('/api/ai-forecast/current', { params: query });
  return data;
}

export async function getAiForecastRolling12(query: AiForecastQuery): Promise<AiForecastRollingResponse> {
  const { data } = await client.get<AiForecastRollingResponse>('/api/ai-forecast/rolling-12', { params: query });
  return data;
}
