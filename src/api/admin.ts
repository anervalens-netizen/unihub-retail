import { client } from './client';
import type {
  AdminUser,
  AdminUserCreate,
  AdminUserUpdate,
} from './types';

export async function getAdminUsers(): Promise<AdminUser[]> {
  const { data } = await client.get<AdminUser[]>('/api/admin/users');
  return data;
}

export async function createAdminUser(payload: AdminUserCreate): Promise<AdminUser> {
  const { data } = await client.post<AdminUser>('/api/admin/users', payload);
  return data;
}

export async function updateAdminUser(id: number, payload: AdminUserUpdate): Promise<AdminUser> {
  const { data } = await client.put<AdminUser>(`/api/admin/users/${id}`, payload);
  return data;
}

export async function updateTlAssignments(id: number, siteCodes: string[]): Promise<AdminUser> {
  const { data } = await client.put<AdminUser>(`/api/admin/users/${id}/assignments`, {
    site_codes: siteCodes,
  });
  return data;
}

export async function deleteAdminUser(id: number): Promise<void> {
  await client.delete(`/api/admin/users/${id}`);
}
