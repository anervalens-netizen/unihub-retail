import { generatedGet, generatedPost } from './generated/client';
import type { RetailOperationPaths } from './generated/contracts';
import type {
  ErpReconciliationAppMetric,
  ErpReconciliationIssue,
  ErpReconciliationMetric,
  ErpReconciliationResponse,
  ImportHistoryEntry,
  ImportJobStatus,
  PromoActualImportResponse,
} from './generated/runtime-types';
import type { GeneratedRequest } from './generated/runtime-types';

export async function uploadSalesFile(
  file: File,
  cutoffDate: string,
): Promise<ImportJobStatus> {
  const formData: GeneratedRequest<'upload_sales_file_api_import_sales_post'> = new FormData();
  formData.append('file', file);
  formData.append('cutoff_date', cutoffDate);
  return generatedPost('upload_sales_file_api_import_sales_post', formData);
}

export async function promoteSalesGeneration(
  snapshotId: number,
  generationToken: string,
  manifestSha256: string,
  overrideReason?: string,
): Promise<ImportJobStatus> {
  const body: GeneratedRequest<'promote_sales_generation_api_import_sales__snapshot_id__promote_post'> = {
    generation_token: generationToken,
    manifest_sha256: manifestSha256,
    override_reason: overrideReason || null,
  };
  const pathParams: RetailOperationPaths['promote_sales_generation_api_import_sales__snapshot_id__promote_post'] = { snapshot_id: snapshotId };
  return await generatedPost(
    'promote_sales_generation_api_import_sales__snapshot_id__promote_post',
    body,
    { pathParams },
  );
}

export async function getImportJobStatus(jobId: string): Promise<ImportJobStatus> {
  const pathParams: RetailOperationPaths['get_import_job_status_api_import_jobs__job_id__get'] = { job_id: jobId };
  return await generatedGet('get_import_job_status_api_import_jobs__job_id__get', {
    pathParams,
  });
}

export async function getImportHistory(signal?: AbortSignal): Promise<ImportHistoryEntry[]> {
  return generatedGet('get_import_history_api_import_history_get', { signal });
}

export async function uploadPromoActualsFile(
  file: File,
  importMonth: string,
  cutoffDate: string,
): Promise<ImportJobStatus> {
  const formData: GeneratedRequest<'upload_promo_actuals_file_api_import_promo_actuals_post'> = new FormData();
  formData.append('file', file);
  formData.append('import_month', importMonth);
  formData.append('cutoff_date', cutoffDate);
  return generatedPost('upload_promo_actuals_file_api_import_promo_actuals_post', formData);
}

export async function uploadErpReconciliationFile(
  file: File,
  importMonth: string,
): Promise<ImportJobStatus> {
  const formData: GeneratedRequest<'reconcile_erp_report_file_api_import_erp_reconciliation_post'> = new FormData();
  formData.append('file', file);
  formData.append('import_month', importMonth);
  return generatedPost('reconcile_erp_report_file_api_import_erp_reconciliation_post', formData);
}

export type {
  ErpReconciliationAppMetric,
  ErpReconciliationIssue,
  ErpReconciliationMetric,
  ErpReconciliationResponse,
  ImportHistoryEntry,
  ImportJobStatus,
  PromoActualImportResponse,
};
