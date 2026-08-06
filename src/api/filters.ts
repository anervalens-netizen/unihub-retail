import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { FilterOptions } from './generated/runtime-types';

export async function getFilterOptions(month: string, signal?: AbortSignal): Promise<FilterOptions> {
  const params: RetailOperationQueries['get_filter_options_api_filters_options_get'] = { month };
  return generatedGet('get_filter_options_api_filters_options_get', { params, signal });
}

export async function getAvailableMonths(signal?: AbortSignal): Promise<string[]> {
  return generatedGet('get_available_months_api_filters_months_get', { signal });
}
