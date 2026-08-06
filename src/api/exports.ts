import { client } from './client';
import { generatedGet, generatedPost } from './generated/client';
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
  return generatedGet('get_catalog_api_exports_catalog_get', undefined, signal);
}

export async function previewExport(request: ExportRequest): Promise<ExportPreview> {
  return generatedPost('preview_export_api_exports_preview_post', request);
}

export async function downloadExport(request: ExportRequest): Promise<Blob> {
  const { data } = await client.post<Blob>('/api/exports/download', request, { responseType: 'blob' });
  return data;
}
