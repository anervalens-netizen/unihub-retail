import { generatedGet } from './generated/client';
import type { AppFilters } from '../components/MainLayout';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';
import type {
  TeamLeaderGroup,
  VisitDayGroup,
  VisitDetail,
  VisitMonthGroup,
  VisitReportResponse,
  VisitReportRow,
  VisitSummaryItem,
  VisitTreeResponse,
} from './generated/runtime-types';

function buildParams(filters: AppFilters): Record<string, string> {
  return {
    ...(filters.firma !== ALL_FIRMS && { firma: filters.firma }),
    ...(filters.rm !== ALL_SCOPE && { rm: filters.rm }),
    ...(filters.magazin !== ALL_STORES && { magazin: filters.magazin }),
  };
}

export async function getVisitsReport(
  month: string,
  filters: AppFilters,
  signal?: AbortSignal,
): Promise<VisitReportResponse> {
  return await generatedGet('get_visits_report_api_visits_report_get', {
    params: { ...buildParams(filters), month },
    signal,
  }) as VisitReportResponse;
}

export async function getVisitsTree(
  month: string,
  filters: AppFilters,
  signal?: AbortSignal,
): Promise<VisitTreeResponse> {
  return await generatedGet('get_visits_tree_api_visits_report_tree_get', {
    params: { ...buildParams(filters), month },
    signal,
  }) as VisitTreeResponse;
}

export async function getVisitDetail(visitId: string, signal?: AbortSignal): Promise<VisitDetail> {
  return await generatedGet('get_visit_detail_api_visits_report_visit__visit_id__get', {
    pathParams: { visit_id: visitId },
    signal,
  }) as VisitDetail;
}

export function getVisitPhotoUrl(visitId: string, filename: string): string {
  return `/api/visits-report/photo/${visitId}/${filename}`;
}

export type {
  TeamLeaderGroup,
  VisitDayGroup,
  VisitDetail,
  VisitMonthGroup,
  VisitReportResponse,
  VisitReportRow,
  VisitSummaryItem,
  VisitTreeResponse,
};
