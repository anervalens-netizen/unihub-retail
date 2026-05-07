import { client } from './client';
import type { ImportHistoryEntry, ImportResponse } from './types';

export async function uploadSalesFile(file: File): Promise<ImportResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post<ImportResponse>('/api/import/sales', formData);
  return data;
}

export async function getImportHistory(): Promise<ImportHistoryEntry[]> {
  const { data } = await client.get<ImportHistoryEntry[]>('/api/import/history');
  return data;
}
