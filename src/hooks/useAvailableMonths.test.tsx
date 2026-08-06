// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import {
  classifyAvailableMonths,
  clearAvailableMonthsCache,
  readCachedMonths,
  useAvailableMonths,
} from './useAvailableMonths';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useAvailableMonths', () => {
  it('clears the session-scoped persistent fallback on logout', () => {
    localStorage.setItem('unihub_available_months_v1', '{"version":1}');
    clearAvailableMonthsCache();
    expect(localStorage.getItem('unihub_available_months_v1')).toBeNull();
  });

  it('classifies empty, stale, and session-expired states explicitly', () => {
    expect(classifyAvailableMonths(true, false, false, null, [], null)).toBe('empty');
    expect(classifyAvailableMonths(true, false, true, new Error('network'), undefined, {
      version: 1,
      months: ['2026-08', '2026-07'],
      savedAt: '2026-08-06T10:00:00.000Z',
    })).toBe('stale');
    expect(classifyAvailableMonths(true, false, true, new ApiError(401, '', null), undefined, null)).toBe('session_expired');
    expect(classifyAvailableMonths(true, false, true, new Error('network'), undefined, null)).toBe('unavailable');
    expect(classifyAvailableMonths(true, false, true, new ApiError(403, '', null), undefined, {
      version: 1,
      months: ['2026-08', '2026-07'],
      savedAt: '2026-08-06T10:00:00.000Z',
    })).toBe('session_expired');
  });

  it('rejects a single saved month as an incomplete stale fallback', () => {
    localStorage.setItem(
      'unihub_available_months_v1',
      JSON.stringify({
        version: 1,
        identityKey: 'subject-single-month',
        months: ['2026-08'],
        savedAt: '2026-08-06T10:00:00.000Z',
      }),
    );

    expect(readCachedMonths('subject-single-month')).toBeNull();
  });

  it('rejects duplicate saved months that normalize to one value', () => {
    localStorage.setItem(
      'unihub_available_months_v1',
      JSON.stringify({
        version: 1,
        identityKey: 'subject-duplicate-month',
        months: ['2026-08', '2026-08'],
        savedAt: '2026-08-06T10:00:00.000Z',
      }),
    );

    expect(readCachedMonths('subject-duplicate-month')).toBeNull();
  });

  it('loads a valid month list and exposes retry without page reload', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(['2026-08', '2026-07']), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { result } = renderHook(() => useAvailableMonths(true), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.months).toEqual(['2026-08', '2026-07']);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });
});
