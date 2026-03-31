import { client } from './client';
import type { Visit } from './types';

export interface VisitFilters {
  month?: string;
  site_code?: string;
  status?: string;
}

export async function getVisits(filters: VisitFilters): Promise<Visit[]> {
  const { data } = await client.get<Visit[]>('/api/visits', { params: filters });
  return data;
}

export async function createVisit(payload: Visit): Promise<Visit> {
  const { data } = await client.post<Visit>('/api/visits', payload);
  return data;
}

export async function updateVisit(payload: Visit): Promise<Visit> {
  const { data } = await client.put<Visit>(`/api/visits/${payload.id}`, payload);
  return data;
}

export async function deleteVisit(id: string): Promise<void> {
  await client.delete(`/api/visits/${id}`);
}
