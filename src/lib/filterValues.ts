import type { AppFilters } from './appFilters';

export const ALL_FIRMS = 'Toate';
export const ALL_SCOPE = 'Toti';
export const ALL_STORES = 'Toate';

export function defaultAppFilters(): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    magazin: [],
    agent: [],
  };
}

export function normalizeAppFilters(value: unknown): AppFilters {
  const candidate = value && typeof value === 'object'
    ? value as Record<string, unknown>
    : {};
  const defaults = defaultAppFilters();
  const readString = (key: 'firma' | 'rm') => (
    typeof candidate[key] === 'string' ? candidate[key] as string : defaults[key]
  );
  const canonicalSelection = (items: unknown[]) => Array.from(new Set(
    items
      .filter((item): item is string => typeof item === 'string')
      .map((item) => item.trim())
      .filter(Boolean),
  ));
  const readSelection = (key: 'magazin' | 'agent') => {
    const raw = candidate[key];
    if (Array.isArray(raw)) {
      return canonicalSelection(raw);
    }
    // One-time migration for session state written by versions that used CSV.
    if (typeof raw === 'string' && raw !== ALL_STORES && raw !== ALL_SCOPE) {
      return canonicalSelection(raw.split(','));
    }
    return defaults[key];
  };

  return {
    firma: readString('firma'),
    rm: readString('rm'),
    magazin: readSelection('magazin'),
    agent: readSelection('agent'),
  };
}
