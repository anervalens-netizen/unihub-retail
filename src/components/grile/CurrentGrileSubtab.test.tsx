// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';

const api = vi.hoisted(() => ({
  getGrileOverview: vi.fn(),
  runGrileCheck: vi.fn(),
}));

vi.mock('../../api/grile', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/grile')>();
  return {
    ...original,
    getGrileOverview: api.getGrileOverview,
    runGrileCheck: api.runGrileCheck,
  };
});

vi.mock('../GrileMonthlyPanel', () => ({
  GrileMonthlyPanel: () => null,
}));

vi.mock('./GrileOverviewTree', () => ({
  GrileOverviewTree: () => null,
}));

import { CurrentGrileSubtab } from './CurrentGrileSubtab';

const MONTH = '2026-08';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const baseOverview = () => ({
  month: MONTH,
  total_sheets: 1,
  run: null,
  summary: {
    business_ok: 1,
    business_problems: 0,
    business_unknown: 0,
    provider_fresh: 1,
    provider_errors: 0,
    provider_stale: 0,
    provider_unknown: 0,
    legacy_completion_windows: 0,
  },
  managers: [],
});

function renderSubtab(month = MONTH) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={client}>
      <CurrentGrileSubtab initialMonth={month} />
    </QueryClientProvider>,
  );
  return { client };
}

const FALLBACK_TEXT = 'Verificarea grilelor nu a putut fi pornită. Încearcă din nou.';
const RUN_BUTTON_LABEL = 'Rulează verificare';
const PENDING_BUTTON_LABEL = 'Rulează…';

describe('CurrentGrileSubtab run-check error visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getGrileOverview.mockResolvedValue(baseOverview());
  });

  afterEach(() => {
    cleanup();
  });

  it('surfaces actionable 403 ApiError detail to the operator', async () => {
    const user = userEvent.setup();
    api.runGrileCheck.mockRejectedValue(
      new ApiError(403, 'Lipsește permisiunea unihub-manager.', null),
    );

    renderSubtab();
    const button = await screen.findByRole('button', { name: RUN_BUTTON_LABEL });
    expect(button).toBeEnabled();

    await user.click(button);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Lipsește permisiunea unihub-manager.');
    // Bounded fallback must not replace the actionable detail.
    expect(alert.textContent ?? '').not.toContain(FALLBACK_TEXT);

    // The button returns to the operator-available state so they can retry.
    expect(await screen.findByRole('button', { name: RUN_BUTTON_LABEL })).toBeEnabled();
  });

  it('clears the previous mutation error while a retry is pending and removes it on success', async () => {
    const user = userEvent.setup();
    const deferred = createDeferred<{ status: 'enqueued' }>();
    api.runGrileCheck
      .mockRejectedValueOnce(
        new ApiError(403, 'Lipsește permisiunea unihub-manager.', null),
      )
      .mockImplementationOnce(() => deferred.promise);

    renderSubtab();
    const firstButton = await screen.findByRole('button', { name: RUN_BUTTON_LABEL });
    await user.click(firstButton);

    const firstAlert = await screen.findByRole('alert');
    expect(firstAlert).toHaveTextContent('Lipsește permisiunea unihub-manager.');

    // Click again to start retry: the previous mutation error must clear immediately
    // while the new mutation is pending.
    const retryButton = await screen.findByRole('button', { name: RUN_BUTTON_LABEL });
    await user.click(retryButton);

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(await screen.findByRole('button', { name: PENDING_BUTTON_LABEL })).toBeDisabled();
    expect(api.runGrileCheck).toHaveBeenCalledTimes(2);

    // Resolve the deferred retry success so onSuccess runs.
    await act(async () => {
      deferred.resolve({ status: 'enqueued' });
      await deferred.promise;
    });

    // After success the alert must not return and the button must be available again.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: RUN_BUTTON_LABEL })).toBeEnabled();
  });

  it('shows the bounded Romanian fallback for 5xx, 429, and ordinary network errors', async () => {
    const user = userEvent.setup();
    const scenarios: Array<[string, unknown]> = [
      ['5xx upstream', new ApiError(500, 'internal stack trace from upstream', null)],
      ['rate-limited 429', new ApiError(429, 'rate limit exceeded - try later', null)],
      ['network failure', new TypeError('Failed to fetch')],
    ];

    for (const [_label, reason] of scenarios) {
      api.runGrileCheck.mockRejectedValueOnce(reason);

      renderSubtab();
      const button = await screen.findByRole('button', { name: RUN_BUTTON_LABEL });
      await user.click(button);

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent(FALLBACK_TEXT);

      // Raw/internal error text must not leak to the operator.
      const text = alert.textContent ?? '';
      expect(text).not.toContain('internal stack trace');
      expect(text).not.toContain('rate limit exceeded');
      expect(text).not.toContain('Failed to fetch');

      cleanup();
    }
  });
});
