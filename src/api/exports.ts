import { client } from './client';

export interface ExportColumnDef {
  key: string;
  label: string;
  type: string;
  group: string;
}

export interface ExportDataset {
  key: string;
  label: string;
  description: string;
  dimensions: ExportColumnDef[];
}

export interface ExportCatalog {
  datasets: ExportDataset[];
  metrics: ExportColumnDef[];
  monthly_metrics: ExportColumnDef[];
  daily_metrics: ExportColumnDef[];
  comparison_levels: Array<{ key: string; label: string }>;
}

export interface ExportFilters {
  firma: string[];
  regional: string[];
  asm: string[];
  site_code: string[];
  agent: string[];
}

export interface ExportRequest {
  export_mode?: 'table' | 'daily_comparison';
  dataset: string;
  months: string[];
  dimensions: string[];
  metrics: string[];
  monthly_metrics: string[];
  daily_metrics: string[];
  comparison_levels?: string[];
  filters: ExportFilters;
  include_closed_stores: boolean;
  preview_limit?: number;
  filename?: string | null;
}

export interface ExportPreview {
  columns: ExportColumnDef[];
  rows: Record<string, string | number | null>[];
  total_rows: number;
  truncated: boolean;
}

export async function getExportCatalog(): Promise<ExportCatalog> {
  const { data } = await client.get<ExportCatalog>('/api/exports/catalog');
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
