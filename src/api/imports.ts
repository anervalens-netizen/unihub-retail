import { client } from './client';
import type { ImportHistoryEntry, ImportJobStatus } from './types';

export interface PromoActualImportResponse {
  import_month: string;
  cutoff_date: string;
  filename: string;
  report_rows: number;
  promo_units: number;
  updated_promotions: number;
}

export async function uploadSalesFile(file: File): Promise<ImportJobStatus> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post<ImportJobStatus>('/api/import/sales', formData);
  return data;
}

export async function getImportJobStatus(jobId: string): Promise<ImportJobStatus> {
  const { data } = await client.get<ImportJobStatus>(
    `/api/import/jobs/${encodeURIComponent(jobId)}`,
  );
  return data;
}

export async function getImportHistory(): Promise<ImportHistoryEntry[]> {
  const { data } = await client.get<ImportHistoryEntry[]>('/api/import/history');
  return data;
}

export async function uploadPromoActualsFile(
  file: File,
  importMonth: string,
  cutoffDate: string,
): Promise<PromoActualImportResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('import_month', importMonth);
  formData.append('cutoff_date', cutoffDate);
  const { data } = await client.post<PromoActualImportResponse>('/api/import/promo-actuals', formData);
  return data;
}
