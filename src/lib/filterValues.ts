import type { AppFilters } from '../components/MainLayout';

export const ALL_FIRMS = 'Toate';
export const ALL_SCOPE = 'Toti';
export const ALL_STORES = 'Toate';

export function defaultAppFilters(): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    asm: ALL_SCOPE,
    magazin: ALL_STORES,
    agent: ALL_SCOPE,
  };
}
