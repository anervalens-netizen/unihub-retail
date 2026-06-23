import { client } from './client';
import type { ImportHistoryEntry, ImportJobStatus } from './types';

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
