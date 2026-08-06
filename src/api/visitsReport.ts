import { generatedGet } from './generated/client';
import type { RetailOperationPaths, RetailOperationQueries } from './generated/contracts';
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

export async function getVisitsReport(
  params: RetailOperationQueries['get_visits_report_api_visits_report_get'],
  signal?: AbortSignal,
): Promise<VisitReportResponse> {
  return await generatedGet('get_visits_report_api_visits_report_get', {
    params,
    signal,
  });
}

export async function getVisitsTree(
  params: RetailOperationQueries['get_visits_tree_api_visits_report_tree_get'],
  signal?: AbortSignal,
): Promise<VisitTreeResponse> {
  return await generatedGet('get_visits_tree_api_visits_report_tree_get', {
    params,
    signal,
  });
}

export async function getVisitDetail(
  visitId: RetailOperationPaths['get_visit_detail_api_visits_report_visit__visit_id__get']['visit_id'],
  signal?: AbortSignal,
): Promise<VisitDetail> {
  return await generatedGet('get_visit_detail_api_visits_report_visit__visit_id__get', {
    pathParams: { visit_id: visitId },
    signal,
  });
}

export async function getVisitPhoto(
  visitId: RetailOperationPaths['get_visit_photo_api_visits_report_photo__visit_id___filename__get']['visit_id'],
  filename: RetailOperationPaths['get_visit_photo_api_visits_report_photo__visit_id___filename__get']['filename'],
  signal?: AbortSignal,
): Promise<Blob> {
  return generatedGet('get_visit_photo_api_visits_report_photo__visit_id___filename__get', {
    pathParams: { visit_id: visitId, filename },
    signal,
  });
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
