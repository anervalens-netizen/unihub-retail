import { generatedGet } from './generated/client';
import type { FilterOptions } from './types';

export async function getFilterOptions(month: string, signal?: AbortSignal): Promise<FilterOptions> {
  return generatedGet('get_filter_options_api_filters_options_get', { month }, signal);
}

export async function getAvailableMonths(signal?: AbortSignal): Promise<string[]> {
  return generatedGet('get_available_months_api_filters_months_get', undefined, signal);
}
