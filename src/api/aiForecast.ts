import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { AiForecastResponse, AiForecastRollingResponse } from './generated/runtime-types';

export type AiForecastQuery = RetailOperationQueries['get_current_ai_forecast_api_ai_forecast_current_get'];

export async function getAiForecastCurrent(query: AiForecastQuery, signal?: AbortSignal): Promise<AiForecastResponse> {
  return generatedGet('get_current_ai_forecast_api_ai_forecast_current_get', { params: query, signal });
}

export async function getAiForecastRolling12(query: RetailOperationQueries['get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get'], signal?: AbortSignal): Promise<AiForecastRollingResponse> {
  return generatedGet('get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get', { params: query, signal });
}
