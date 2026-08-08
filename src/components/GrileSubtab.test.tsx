// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { GrileOverview, GrileRun, GrileStore } from '../api/grile';

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
  summary: {
    business_ok: 0,
    business_problems: 0,
    business_unknown: 2,
    provider_fresh: 0,
    provider_errors: 0,
    provider_stale: 0,
    provider_unknown: 2,
    legacy_completion_windows: 0,
  },
  managers: [],
});

const store = (): GrileStore => ({
  site_code: 'S001',
  sheet_id: 'sheet-1',
  locatie: 'Magazin Test',
  firma: 'Mobiup',
  regional: 'RM Test',
  asm: 'ASM Test',
  team_leader_name: null,
  completion_pct: 50,
  last_edit: null,
  checked_at: null,
  grila_target: 100,
  grila_sales: 50,
  db_target: 100,
  db_sales_mtd: 50,
  target_diff: 0,
  sales_diff: 0,
  db_max_sale_date: null,
  fill_status: 'COMPLETAT',
  target_status: 'OK',
  sales_status: 'OK',
  missing_days: [],
  days_elapsed: 6,
  completion_algorithm_version: 2,
  completion_as_of: '2026-08-07',
  completion_window_status: 'current',
  provider_status: {
    state: 'fresh',
    last_attempt_at: '2026-08-07T08:00:00Z',
    last_success_at: '2026-08-07T08:00:00Z',
    last_error_at: null,
    last_error_code: null,
    last_error_message: null,
    stale_age_seconds: 0,
  },
  error_code: null,
  error_message: null,
});

const overviewWithStore = (): GrileOverview => ({
  month: '2026-08',
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
  managers: [{
    name: 'ASM Test',
    store_count: 1,
    ok: 1,
    problems: 0,
    business_unknown: 0,
    provider_fresh: 1,
    provider_errors: 0,
    provider_stale: 0,
    provider_unknown: 0,
    legacy_completion_windows: 0,
    avg_completion: 50,
    team_leaders: [{ name: null, firms: [{ name: 'Mobiup', stores: [store()] }] }],
  }],
});

describe('Grile run authority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
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

  it('shows the explicit unknown-state warning instead of claiming refresh failure or success', async () => {
    api.getGrileOverview.mockResolvedValue(overviewWithStore());
    api.refreshGrileStore.mockRejectedValue(
      new Error(
        'Starea verificării 41 nu poate fi confirmată. Nu relansa verificarea până când operația nu este verificată în backend.',
      ),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <GrileSubtab initialMonth="2026-08" />
      </QueryClientProvider>,
    );

    const refreshButtons = await screen.findAllByRole('button', {
      name: 'Reîmprospătează grila Magazin Test',
    });
    // StoreRow intentionally exposes equivalent mobile and desktop controls;
    // exercise one rendered control and verify the shared mutation state.
    expect(refreshButtons.length).toBeGreaterThan(0);
    await user.click(refreshButtons[0]!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Nu relansa verificarea');
  });
});
