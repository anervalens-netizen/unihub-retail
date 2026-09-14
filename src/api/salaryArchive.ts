import { generatedGet } from './generated/client';
import type { RetailOperationQueries, RetailSalaryArchiveResponse, RetailSalaryArchiveSummary } from './generated/contracts';
import type { RequiredRuntime } from './generated/runtime-types';

export type SalaryArchiveResponse = RequiredRuntime<RetailSalaryArchiveResponse>;
export type SalaryArchiveItem = SalaryArchiveResponse['items'][number];
export type SalaryArchiveQuery = RetailOperationQueries['salary_archive_salarii_archive_get'];

export function fetchSalaryArchive(params: SalaryArchiveQuery, signal?: AbortSignal): Promise<SalaryArchiveResponse> {
  return generatedGet('salary_archive_salarii_archive_get', { params, signal });
}

export type SalaryArchiveSummary = RequiredRuntime<RetailSalaryArchiveSummary>;
export function fetchSalaryArchiveSummary(params: RetailOperationQueries['salary_archive_summary_salarii_archive_summary_get'], signal?: AbortSignal): Promise<SalaryArchiveSummary> {
  return generatedGet('salary_archive_summary_salarii_archive_summary_get', { params, signal });
}
