import { client } from './client';
import type {
  RetailExportCatalogResponse,
  RetailExportColumnDef,
  RetailExportFilters,
  RetailExportPreviewResponse,
  RetailExportRequest,
} from './generated/contracts';

export type ExportColumnDef = RetailExportColumnDef;
export type ExportCatalog = RetailExportCatalogResponse;
export type ExportFilters = Required<RetailExportFilters>;
export type ExportRequest = RetailExportRequest;
export type ExportPreview = RetailExportPreviewResponse;

export async function getExportCatalog(signal?: AbortSignal): Promise<ExportCatalog> {
  const { data } = await client.get<ExportCatalog>('/api/exports/catalog', { signal });
  return data;
}

export async function previewExport(request: ExportRequest): Promise<ExportPreview> {
  const { data } = await client.post<ExportPreview>('/api/exports/preview', request);
  return data;
}

export async function downloadExport(request: ExportRequest): Promise<Blob> {
  const { data } = await client.post<Blob>('/api/exports/download', request, { responseType: 'blob' });
  return data;
}
