import { client } from './client';
import type { AuthUser, LoginResponse } from './types';

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>('/api/auth/login', { username, password });
  localStorage.setItem('unihub_token', data.access_token);
  return data;
}

export function logout(): void {
  localStorage.removeItem('unihub_token');
}

export async function getCurrentUser(): Promise<AuthUser> {
  const { data } = await client.get<AuthUser>('/api/auth/me');
  return data;
}
