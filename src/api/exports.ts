import { generatedGet, generatedPost, isGeneratedApiError } from './generated/client';
import type {
  RetailExportCatalogResponse,
  RetailExportColumnDef,
  RetailExportFilters,
  RetailExportOperationResponse,
  RetailExportPreviewResponse,
  RetailOperationPaths,
} from './generated/contracts';
import type { GeneratedRequest, RequiredRuntime } from './generated/runtime-types';

export type ExportColumnDef = RetailExportColumnDef;
export type ExportCatalog = RetailExportCatalogResponse;
export type ExportFilters = Required<RetailExportFilters>;
export type ExportRequest = GeneratedRequest<'preview_export_api_exports_preview_post'>;
export type ExportPreview = RetailExportPreviewResponse;
export type ExportOperation = RequiredRuntime<RetailExportOperationResponse>;

export async function getExportCatalog(signal?: AbortSignal): Promise<ExportCatalog> {
  return generatedGet('get_catalog_api_exports_catalog_get', { signal });
}

export async function previewExport(
  request: GeneratedRequest<'preview_export_api_exports_preview_post'>,
): Promise<ExportPreview> {
  return generatedPost('preview_export_api_exports_preview_post', request);
}

export async function downloadExport(
  request: GeneratedRequest<'download_export_api_exports_download_post'>,
): Promise<Blob> {
  return generatedPost('download_export_api_exports_download_post', request);
}

export async function createExportOperation(
  request: GeneratedRequest<'create_export_operation_api_exports_operations_post'>,
): Promise<ExportOperation> {
  return generatedPost('create_export_operation_api_exports_operations_post', request);
}

export async function getResumableExportOperation(signal?: AbortSignal): Promise<ExportOperation | null> {
  return generatedGet('get_resumable_export_operation_api_exports_operations_resumable_get', { signal });
}

export async function getExportOperation(
  operationId: RetailOperationPaths['get_export_operation_api_exports_operations__operation_id__get']['operation_id'],
  signal?: AbortSignal,
): Promise<ExportOperation> {
  return generatedGet('get_export_operation_api_exports_operations__operation_id__get', {
    pathParams: { operation_id: operationId },
    signal,
  });
}

export async function cancelExportOperation(
  operationId: RetailOperationPaths['cancel_export_operation_api_exports_operations__operation_id__cancel_post']['operation_id'],
): Promise<ExportOperation> {
  return generatedPost(
    'cancel_export_operation_api_exports_operations__operation_id__cancel_post',
    undefined,
    { pathParams: { operation_id: operationId } },
  );
}

export async function downloadExportOperation(
  operationId: RetailOperationPaths['download_export_operation_api_exports_operations__operation_id__download_get']['operation_id'],
  signal?: AbortSignal,
): Promise<Blob> {
  return generatedGet(
    'download_export_operation_api_exports_operations__operation_id__download_get',
    { pathParams: { operation_id: operationId }, signal },
  );
}

export function isExportOperationNotFound(error: unknown): boolean {
  return isGeneratedApiError(
    error,
    'get_export_operation_api_exports_operations__operation_id__get',
  ) && error.status === 404;
}

export function uncertainExportOperationId(error: unknown): number | null {
  const operationId = 'create_export_operation_api_exports_operations_post';
  if (!isGeneratedApiError(error, operationId) || error.status !== 503) {
    return null;
  }
  const body = error.typedBody;
  if (!body || typeof body !== 'object' || !('detail' in body)) return null;
  const detail = body.detail;
  if (!detail || typeof detail !== 'object' || !('operation_id' in detail)) return null;
  const candidate = detail.operation_id;
  return typeof candidate === 'number' && Number.isInteger(candidate) && candidate > 0
    ? candidate
    : null;
}
