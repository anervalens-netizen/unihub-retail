import type { DashboardQuery } from '../api/dashboard';
import type { AppFilters } from '../components/MainLayout';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from './filterValues';

export function buildScopedMonthQuery(
  month: string,
  filters: AppFilters
): DashboardQuery {
  return {
    month,
    firma: filters.firma === ALL_FIRMS ? undefined : filters.firma,
    regional: filters.rm === ALL_SCOPE ? undefined : filters.rm,
    site_code: filters.magazin === ALL_STORES ? undefined : filters.magazin,
    agent: filters.agent === ALL_SCOPE ? undefined : filters.agent,
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
