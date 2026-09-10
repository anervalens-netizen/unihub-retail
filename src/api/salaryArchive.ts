import { generatedGet } from './generated/client';
import type { RetailOperationQueries, RetailSalaryArchiveResponse } from './generated/contracts';
import type { RequiredRuntime } from './generated/runtime-types';

export type SalaryArchiveResponse = RequiredRuntime<RetailSalaryArchiveResponse>;
export type SalaryArchiveItem = SalaryArchiveResponse['items'][number];
export type SalaryArchiveQuery = RetailOperationQueries['salary_archive_salarii_archive_get'];

export function fetchSalaryArchive(params: SalaryArchiveQuery, signal?: AbortSignal): Promise<SalaryArchiveResponse> {
  return generatedGet('salary_archive_salarii_archive_get', { params, signal });
}
