import type { AppFilters } from '../components/MainLayout';

export const ALL_FIRMS = 'Toate';
export const ALL_SCOPE = 'Toti';
export const ALL_STORES = 'Toate';

export function defaultAppFilters(): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    magazin: ALL_STORES,
    agent: ALL_SCOPE,
  };
}

export function normalizeAppFilters(value: unknown): AppFilters {
  const candidate = value && typeof value === 'object'
    ? value as Record<string, unknown>
    : {};
  const defaults = defaultAppFilters();
  const readString = (key: keyof AppFilters) => (
    typeof candidate[key] === 'string' ? candidate[key] as string : defaults[key]
  );

  return {
    firma: readString('firma'),
    rm: readString('rm'),
    magazin: readString('magazin'),
    agent: readString('agent'),
  };
}
