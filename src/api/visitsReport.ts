import { client } from './client';
import type { AppFilters } from '../components/MainLayout';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';

export interface VisitReportRow {
  magazin: string;
  asm: string | null;
  regional: string | null;
  firma: string | null;
  nr_vizite: number;
  avg_completion: number;
  curatenie_pct: number;
  imagine_pct: number;
  uniforma_pct: number;
  afise_pct: number;
  produse_promo_pct: number;
  last_visit: string | null;
}

export interface VisitReportResponse {
  month: string;
  total_vizite: number;
  magazine_unice: number;
  avg_completion: number;
  rows: VisitReportRow[];
}

export async function getVisitsReport(
  month: string,
  filters: AppFilters
): Promise<VisitReportResponse> {
  const params = new URLSearchParams({ month });
  if (filters.firma !== ALL_FIRMS) params.set('firma', filters.firma);
  if (filters.rm !== ALL_SCOPE) params.set('rm', filters.rm);
  if (filters.asm !== ALL_SCOPE) params.set('asm', filters.asm);
  if (filters.magazin !== ALL_STORES) params.set('magazin', filters.magazin);
  const response = await client.get<VisitReportResponse>(`/api/visits-report?${params}`);
  return response.data;
}
