import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo } from 'react';

import { getAvailableMonths } from '../api/filters';
import { ApiError } from '../api/client';

export const AVAILABLE_MONTHS_QUERY_KEY = ['filters', 'available-months'] as const;
const AVAILABLE_MONTHS_CACHE_KEY = 'unihub_available_months_v1';
const MIN_CACHED_MONTHS = 1;

export function clearAvailableMonthsCache(): void {
  try {
    window.localStorage.removeItem(AVAILABLE_MONTHS_CACHE_KEY);
  } catch {
    // Storage can be disabled; the in-memory query cache is cleared separately.
  }
}

type CachedMonths = {
  version: 1;
  identityKey?: string;
  months: string[];
  savedAt: string;
};

export type AvailableMonthsStatus =
  | 'loading'
  | 'ready'
  | 'empty'
  | 'stale'
  | 'unavailable'
  | 'session_expired';

export type AvailableMonthsState = {
  months: string[];
  status: AvailableMonthsStatus;
  isLoading: boolean;
  isFetching: boolean;
  error: unknown;
  staleAt: string | null;
  retry: () => Promise<unknown>;
  setMonths: (months: string[] | ((previous: string[]) => string[])) => void;
};

export function readCachedMonths(identityKey: string): CachedMonths | null {
  try {
    const raw = window.localStorage.getItem(AVAILABLE_MONTHS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CachedMonths>;
    if (
      parsed.version !== 1 ||
      parsed.identityKey !== identityKey ||
      !Array.isArray(parsed.months) ||
      parsed.months.length < MIN_CACHED_MONTHS ||
      !parsed.months.every((month): month is string => /^\d{4}-(0[1-9]|1[0-2])$/.test(month)) ||
      typeof parsed.savedAt !== 'string'
    ) {
      return null;
    }
    return { version: 1, months: [...new Set(parsed.months)].sort().reverse(), savedAt: parsed.savedAt };
  } catch {
    return null;
  }
}

function writeCachedMonths(months: string[], identityKey: string): void {
  if (months.length < MIN_CACHED_MONTHS) return;
  try {
    const payload: CachedMonths = {
      version: 1,
      identityKey,
      months: [...new Set(months)].sort().reverse(),
      savedAt: new Date().toISOString(),
    };
    window.localStorage.setItem(AVAILABLE_MONTHS_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Storage is an optimization; a disabled or full browser cache is safe.
  }
}

function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

function shouldRetry(error: unknown, failureCount: number): boolean {
  if (failureCount >= 2 || isSessionExpired(error)) return false;
  return true;
}

export function classifyAvailableMonths(
  authenticated: boolean,
  isPending: boolean,
  isError: boolean,
  error: unknown,
  months: string[] | undefined,
  cached: CachedMonths | null,
): AvailableMonthsStatus {
  if (!authenticated) return 'empty';
  if (isPending) return 'loading';
  if (!isError) return months?.length ? 'ready' : 'empty';
  if (isSessionExpired(error)) return 'session_expired';
  return cached ? 'stale' : 'unavailable';
}

export function useAvailableMonths(
  authenticated: boolean,
  identityKey = 'authenticated',
): AvailableMonthsState {
  const queryClient = useQueryClient();
  const cached = useMemo(
    () => (authenticated ? readCachedMonths(identityKey) : null),
    [authenticated, identityKey],
  );
  const queryKey = useMemo(
    () => [...AVAILABLE_MONTHS_QUERY_KEY, identityKey] as const,
    [identityKey],
  );
  const query = useQuery({
    queryKey,
    enabled: authenticated,
    queryFn: ({ signal }) => getAvailableMonths(signal),
    retry: shouldRetry,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });

  useEffect(() => {
    if (query.data) writeCachedMonths(query.data, identityKey);
  }, [identityKey, query.data]);

  const setMonths = useCallback(
    (next: string[] | ((previous: string[]) => string[])) => {
      queryClient.setQueryData<string[]>(queryKey, (previous = []) =>
        typeof next === 'function' ? next(previous) : next,
      );
    },
    [queryClient, queryKey],
  );

  const status = classifyAvailableMonths(
    authenticated,
    query.isPending,
    query.isError,
    query.error,
    query.data,
    cached,
  );
  const months = query.data ?? (status === 'stale' ? cached?.months : undefined) ?? [];

  return {
    months,
    status,
    isLoading: authenticated && query.isPending,
    isFetching: query.isFetching,
    error: query.error,
    staleAt: status === 'stale' ? cached?.savedAt ?? null : null,
    retry: query.refetch,
    setMonths,
  };
}
