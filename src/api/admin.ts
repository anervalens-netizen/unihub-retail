import { client } from './client';
import type {
  AdminUser,
  AdminUserCreate,
  AdminUserUpdate,
  FocusProduct,
  FocusProductCreate,
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

export async function getFocusProducts(): Promise<FocusProduct[]> {
  const { data } = await client.get<FocusProduct[]>('/api/admin/focus-products');
  return data;
}

export async function createFocusProduct(payload: FocusProductCreate): Promise<FocusProduct> {
  const { data } = await client.post<FocusProduct>('/api/admin/focus-products', payload);
  return data;
}

export async function deleteFocusProduct(itemCode: string): Promise<void> {
  await client.delete(`/api/admin/focus-products/${itemCode}`);
}

export async function deleteAdminUser(id: number): Promise<void> {
  await client.delete(`/api/admin/users/${id}`);
}
