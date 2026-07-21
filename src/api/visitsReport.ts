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

export interface VisitSummaryItem {
  id: string;
  magazin: string;
  locatie: string | null;
  ora: string | null;
  completion_pct: number;
  firma: string | null;
  has_photos: boolean;
}

export interface VisitDayGroup {
  date: string;
  nr_vizite: number;
  visits: VisitSummaryItem[];
}

export interface VisitMonthGroup {
  month: string;
  nr_vizite: number;
  days: VisitDayGroup[];
}

export interface TeamLeaderGroup {
  team_leader: string;
  nr_vizite: number;
  months: VisitMonthGroup[];
}

export interface VisitTreeResponse {
  team_leaders: TeamLeaderGroup[];
}

export interface VisitDetail {
  id: string;
  data_raport: string | null;
  ora_trimitere: string | null;
  firma: string | null;
  regional: string | null;
  asm: string | null;
  team_leader: string | null;
  magazin: string | null;
  durata_vizita_ore: number | null;
  curatenie: boolean;
  imagine: boolean;
  uniforma: boolean;
  afise: boolean;
  produse_promo: boolean;
  tpu: number | null;
  sticla: number | null;
  altele: number | null;
  avizat: boolean;
  charisma: number | null;
  casa: number | null;
  incarcari_epay: number | null;
  incarcari_charisma: number | null;
  agent1_nume: string | null;
  agent1_perf: number | null;
  agent1_doi_pe_bon: number | null;
  agent1_focus: number | null;
  agent1_analiza: string | null;
  agent1_plan: string | null;
  agent2_nume: string | null;
  agent2_perf: number | null;
  agent2_doi_pe_bon: number | null;
  agent2_focus: number | null;
  agent2_analiza: string | null;
  agent2_plan: string | null;
  photos: string[];
  completion_pct: number;
  notes: string | null;
}

function buildParams(filters: AppFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.firma !== ALL_FIRMS) params.set('firma', filters.firma);
  if (filters.rm !== ALL_SCOPE) params.set('rm', filters.rm);
  if (filters.magazin !== ALL_STORES) params.set('magazin', filters.magazin);
  return params;
}

export async function getVisitsReport(
  month: string,
  filters: AppFilters,
  signal?: AbortSignal,
): Promise<VisitReportResponse> {
  const params = buildParams(filters);
  params.set('month', month);
  const response = await client.get<VisitReportResponse>(`/api/visits-report?${params}`, { signal });
  return response.data;
}

export async function getVisitsTree(
  month: string,
  filters: AppFilters,
  signal?: AbortSignal,
): Promise<VisitTreeResponse> {
  const params = buildParams(filters);
  params.set('month', month);
  const response = await client.get<VisitTreeResponse>(`/api/visits-report/tree?${params}`, { signal });
  return response.data;
}

export async function getVisitDetail(visitId: string, signal?: AbortSignal): Promise<VisitDetail> {
  const response = await client.get<VisitDetail>(`/api/visits-report/visit/${visitId}`, { signal });
  return response.data;
}

export function getVisitPhotoUrl(visitId: string, filename: string): string {
  return `/api/visits-report/photo/${visitId}/${filename}`;
}
