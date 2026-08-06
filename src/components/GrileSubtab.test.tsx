// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { GrileOverview, GrileRun } from '../api/grile';

const api = vi.hoisted(() => ({
  getGrileOverview: vi.fn(),
  refreshGrileStore: vi.fn(),
  runGrileCheck: vi.fn(),
}));

vi.mock('../api/grile', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/grile')>();
  return {
    ...original,
    getGrileOverview: api.getGrileOverview,
    refreshGrileStore: api.refreshGrileStore,
    runGrileCheck: api.runGrileCheck,
  };
});

vi.mock('./GrileMonthlyPanel', () => ({
  GrileMonthlyPanel: () => null,
}));

import { GrileSubtab } from './GrileSubtab';

const run = (overrides: Partial<GrileRun> = {}): GrileRun => ({
  id: 192,
  run_month: '2026-08',
  source: 'manual',
  source_snapshot_id: null,
  status: 'running',
  active: true,
  progress_current: 1,
  progress_total: 2,
  ok_count: 0,
  problem_count: 0,
  error_count: 0,
  duration_ms: null,
  error_message: null,
  started_at: '2026-08-06T10:00:00Z',
  heartbeat_at: '2026-08-06T10:00:30Z',
  finished_at: null,
  created_at: '2026-08-06T10:00:00Z',
  ...overrides,
});

const overview = (currentRun: GrileRun): GrileOverview => ({
  month: '2026-08',
  total_sheets: 2,
  run: currentRun,
  managers: [],
});

describe('Grile run authority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks only an authoritative active run and re-enables after terminal state', async () => {
    api.getGrileOverview.mockResolvedValue(overview(run()));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <GrileSubtab initialMonth="2026-08" />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('button', { name: 'Rulează…' })).toBeDisabled();
    client.setQueryData(
      ['grile-overview', '2026-08'],
      overview(run({ status: 'failed', active: false, error_message: 'lease expired' })),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Rulează verificare' })).toBeEnabled(),
    );
  });

  it('does not trust a stale raw running label when backend marks it inactive', async () => {
    api.getGrileOverview.mockResolvedValue(overview(run({ active: false })));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <GrileSubtab initialMonth="2026-08" />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('button', { name: 'Rulează verificare' })).toBeEnabled();
  });
});
