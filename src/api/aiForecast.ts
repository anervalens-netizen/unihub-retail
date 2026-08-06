import { generatedGet } from './generated/client';
import type { AiForecastMetric, AiForecastResponse, AiForecastRollingResponse } from './generated/runtime-types';

export type AiForecastQuery = {
  month: string;
  metric?: AiForecastMetric;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
};

export async function getAiForecastCurrent(query: AiForecastQuery, signal?: AbortSignal): Promise<AiForecastResponse> {
  return await generatedGet('get_current_ai_forecast_api_ai_forecast_current_get', { params: query, signal }) as AiForecastResponse;
}

export async function getAiForecastRolling12(query: AiForecastQuery, signal?: AbortSignal): Promise<AiForecastRollingResponse> {
  return await generatedGet('get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get', { params: query, signal }) as AiForecastRollingResponse;
}
