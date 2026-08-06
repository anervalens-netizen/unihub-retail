import { generatedGet, generatedPost } from './generated/client';
import type {
  ErpReconciliationAppMetric,
  ErpReconciliationIssue,
  ErpReconciliationMetric,
  ErpReconciliationResponse,
  ImportHistoryEntry,
  ImportJobStatus,
  PromoActualImportResponse,
} from './generated/runtime-types';

export async function uploadSalesFile(
  file: File,
  cutoffDate: string,
): Promise<ImportJobStatus> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('cutoff_date', cutoffDate);
  return await generatedPost('upload_sales_file_api_import_sales_post', formData) as ImportJobStatus;
}

export async function promoteSalesGeneration(
  snapshotId: number,
  generationToken: string,
  manifestSha256: string,
  overrideReason?: string,
): Promise<ImportJobStatus> {
  return await generatedPost(
    'promote_sales_generation_api_import_sales__snapshot_id__promote_post',
    {
      generation_token: generationToken,
      manifest_sha256: manifestSha256,
      override_reason: overrideReason || null,
    },
    { pathParams: { snapshot_id: snapshotId } },
  ) as ImportJobStatus;
}

export async function getImportJobStatus(jobId: string): Promise<ImportJobStatus> {
  return await generatedGet('get_import_job_status_api_import_jobs__job_id__get', {
    pathParams: { job_id: jobId },
  }) as ImportJobStatus;
}

export async function getImportHistory(): Promise<ImportHistoryEntry[]> {
  return await generatedGet('get_import_history_api_import_history_get') as ImportHistoryEntry[];
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
  return await generatedPost('upload_promo_actuals_file_api_import_promo_actuals_post', formData) as PromoActualImportResponse;
}

export async function uploadErpReconciliationFile(
  file: File,
  importMonth: string,
): Promise<ErpReconciliationResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('import_month', importMonth);
  return await generatedPost('reconcile_erp_report_file_api_import_erp_reconciliation_post', formData) as ErpReconciliationResponse;
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
