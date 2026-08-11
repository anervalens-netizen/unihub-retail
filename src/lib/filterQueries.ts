import type { DashboardQuery } from '../api/dashboard';
import type { AppFilters } from './appFilters';
import { ALL_FIRMS, ALL_SCOPE } from './filterValues';

export function buildScopedMonthQuery(
  month: string,
  filters: AppFilters
): DashboardQuery {
  return {
    month,
    firma: filters.firma === ALL_FIRMS ? undefined : filters.firma,
    regional: filters.rm === ALL_SCOPE ? undefined : filters.rm,
    site_code: filters.magazin.length > 0 ? filters.magazin : undefined,
    agent: filters.agent.length > 0 ? filters.agent : undefined,
  };
}

export function buildCurrentDashboardQuery(
  month: string,
  filters: AppFilters
): DashboardQuery {
  return {
    ...buildScopedMonthQuery(month, filters),
    current_scope: true,
    include_closed_stores: false,
  };
}
