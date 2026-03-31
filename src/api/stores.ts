import { client } from './client';
import type { StoreOption, StoreTargetInput } from './types';

export async function getStores(): Promise<StoreOption[]> {
  const { data } = await client.get<StoreOption[]>('/api/stores');
  return data;
}

export async function saveStoreTargets(payload: StoreTargetInput[]): Promise<{ inserted: number }> {
  const { data } = await client.post<{ inserted: number }>('/api/stores/targets', payload);
  return data;
}
