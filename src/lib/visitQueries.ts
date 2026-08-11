import type { RetailOperationQueries } from "../api/generated/contracts";
import type { AppFilters } from "./appFilters";
import { ALL_FIRMS, ALL_SCOPE } from "./filterValues";

export function buildVisitsReportQuery(
  month: string,
  filters: AppFilters,
): RetailOperationQueries['get_visits_report_api_visits_report_get'] {
  return {
    month,
    ...(filters.firma !== ALL_FIRMS && { firma: filters.firma }),
    ...(filters.rm !== ALL_SCOPE && { rm: filters.rm }),
    ...(filters.magazin.length > 0 && { magazin: filters.magazin }),
  };
}

export function buildVisitsTreeQuery(
  month: string,
  filters: AppFilters,
): RetailOperationQueries['get_visits_tree_api_visits_report_tree_get'] {
  return buildVisitsReportQuery(month, filters);
}
