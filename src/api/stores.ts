import { client } from './client';
import type { StoreOption } from './types';

export async function getStores(): Promise<StoreOption[]> {
  const { data } = await client.get<StoreOption[]>('/api/stores');
  return data;
}
