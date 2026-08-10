import type { GrileStore } from '../../api/grile';

export type StatusFilter =
  | 'all'
  | 'NECOMPLETAT'
  | 'IN_URMA'
  | 'DIF_TARGET'
  | 'DIF_SALES'
  | 'ERROR'
  | 'STALE'
  | 'UNKNOWN'
  | 'OK';

export const GRILE_STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'Toate' },
  { id: 'OK', label: 'OK' },
  { id: 'NECOMPLETAT', label: 'Necompletat' },
  { id: 'IN_URMA', label: 'În urmă' },
  { id: 'DIF_TARGET', label: 'Dif. target' },
  { id: 'DIF_SALES', label: 'Dif. vânzări' },
  { id: 'ERROR', label: 'Eroare Google' },
  { id: 'STALE', label: 'Date vechi' },
  { id: 'UNKNOWN', label: 'Neverificat' },
];

export function matchesGrileStatusFilter(store: GrileStore, filter: StatusFilter): boolean {
  switch (filter) {
    case 'all':
      return true;
    case 'OK':
      return store.target_status === 'OK' && store.sales_status === 'OK';
    case 'NECOMPLETAT':
      return store.fill_status === 'NECOMPLETAT';
    case 'IN_URMA':
      return store.sales_status === 'IN_URMA';
    case 'DIF_TARGET':
      return store.target_status === 'DIFERENTA';
    case 'DIF_SALES':
      return store.sales_status === 'DIFERENTA';
    case 'ERROR':
      return store.provider_status.state === 'error';
    case 'STALE':
      return store.provider_status.state === 'stale';
    case 'UNKNOWN':
      return store.provider_status.state === 'unknown';
    default:
      return true;
  }
}
