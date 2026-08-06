import { generatedGet, generatedPost } from './generated/client';
import type { ImportHistoryEntry, ImportJobStatus } from './types';

export interface PromoActualImportResponse {
  import_month: string;
  cutoff_date: string;
  filename: string;
  report_rows: number;
  promo_units: number;
  updated_promotions: number;
  generation_id: string;
  config_sha256: string;
  source_sha256: string;
  material_sha256: string;
}

export type ErpReconciliationStatus = 'ok' | 'explained' | 'difference' | 'not_comparable';

export interface ErpReconciliationMetric {
  key: string;
  label: string;
  report_value: number | null;
  retail_value: number | null;
  difference: number | null;
  unit: 'RON' | 'buc' | 'bonuri' | 'magazine' | 'agenti';
  status: ErpReconciliationStatus;
  note: string | null;
}

export interface ErpReconciliationIssue {
  severity: 'warning' | 'error';
  scope: 'report' | 'store' | 'agent';
  site_code: string | null;
  entity: string;
  metric: string;
  report_value: number | null;
  retail_value: number | null;
  difference: number | null;
  note: string;
}

export interface ErpReconciliationAppMetric {
  key: string;
  label: string;
  value: number | null;
  unit: 'RON' | 'buc';
  note: string;
}

export interface ErpReconciliationResponse {
  status: 'ok' | 'differences';
  import_month: string;
  report_cutoff_date: string;
  retail_cutoff_date: string | null;
  cutoff_matches: boolean;
  filename: string;
  file_digest: string;
  report_store_count: number;
  retail_store_count: number;
  report_agent_count: number;
  retail_agent_count: number;
  metrics: ErpReconciliationMetric[];
  app_only_metrics: ErpReconciliationAppMetric[];
  issues: ErpReconciliationIssue[];
  issue_count: number;
  omitted_issue_count: number;
  notes: string[];
}

export async function uploadSalesFile(
  file: File,
  cutoffDate: string,
): Promise<ImportJobStatus> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('cutoff_date', cutoffDate);
  return generatedPost('upload_sales_file_api_import_sales_post', formData) as unknown as ImportJobStatus;
}

export async function promoteSalesGeneration(
  snapshotId: number,
  generationToken: string,
  manifestSha256: string,
  overrideReason?: string,
): Promise<ImportJobStatus> {
  return generatedPost(
    'promote_sales_generation_api_import_sales__snapshot_id__promote_post',
    {
      generation_token: generationToken,
      manifest_sha256: manifestSha256,
      override_reason: overrideReason || null,
    },
    { pathParams: { snapshot_id: snapshotId } },
  ) as unknown as ImportJobStatus;
}

export async function getImportJobStatus(jobId: string): Promise<ImportJobStatus> {
  return generatedGet('get_import_job_status_api_import_jobs__job_id__get', {
    pathParams: { job_id: jobId },
  }) as unknown as ImportJobStatus;
}

export async function getImportHistory(): Promise<ImportHistoryEntry[]> {
  return generatedGet('get_import_history_api_import_history_get') as unknown as ImportHistoryEntry[];
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
  return generatedPost('upload_promo_actuals_file_api_import_promo_actuals_post', formData) as unknown as PromoActualImportResponse;
}

export async function uploadErpReconciliationFile(
  file: File,
  importMonth: string,
): Promise<ErpReconciliationResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('import_month', importMonth);
  return generatedPost('reconcile_erp_report_file_api_import_erp_reconciliation_post', formData) as unknown as ErpReconciliationResponse;
}
