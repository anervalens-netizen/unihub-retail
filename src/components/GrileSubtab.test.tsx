// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { GrileOverview, GrileRun, GrileStore } from '../api/grile';

const api = vi.hoisted(() => ({
  getGrileOverview: vi.fn(),
  getGrilePilotV2: vi.fn(),
  refreshGrileStore: vi.fn(),
  runGrileCheck: vi.fn(),
}));

vi.mock('../api/grile', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/grile')>();
  return {
    ...original,
    getGrileOverview: api.getGrileOverview,
    getGrilePilotV2: api.getGrilePilotV2,
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

const pilotOverview = () => ({
  month: '2026-08',
  store_count: 5,
  managers: [
    {
      name: 'Andrei Stancu',
      stores: [
        ['PROMEN', 'Mobicell Promenada', 'MobiCell', '1jcVCLHaujv0O2qlTPXG7b1IqGGVq8572p7pJFvEAgdg'], // pragma: allowlist secret
        ['MCRFBAL', 'Mobiup Carrefour Balotești', 'Mobiup', '1MusUrpTjkFyW2JefvJVdFOdx5ypUbKr1Hs-2SViihEo'], // pragma: allowlist secret
        ['CRFFEER', 'Mobiup Carrefour Feeria', 'Mobiup', '1bEWiDcg9tqWPeqQdw6hna_lsIIc16ozKMCutkVIAHu0'], // pragma: allowlist secret
      ].map(([site_code, locatie, firma, sheet_id]) => ({
        site_code, locatie, firma, sheet_id, manager: 'Andrei Stancu',
        target_v2: 74000, realized_v2: 13636, realized_pct_v2: 18.4,
        forecast_v2: 43911, forecast_pct_v2: 59.3, report_cutoff: '2026-08-09',
        report_check: { status: 'ok', message: 'OK', target: 74000, realized: 13636, target_diff: 0, realized_diff: 0 },
        v1_check: { status: 'ok', message: 'OK', target: 74000, realized: 13636, target_diff: 0, realized_diff: 0 },
      })),
    },
    {
      name: 'Bogdana Costan',
      stores: [
        ['ORAUCHAN', 'Mobicell Oradea Auchan', 'MobiCell', '1ZxugdHXXhvPSFyxyOh9bipq11J2N872n7isAxRXMxuM'], // pragma: allowlist secret
        ['ORAUCH', 'Mobiup Oradea Auchan', 'Mobiup', '12ejRCcDRNdQqiz38S7BjTKNb-pSrJWW2UNclhFJUiCI'], // pragma: allowlist secret
      ].map(([site_code, locatie, firma, sheet_id]) => ({
        site_code, locatie, firma, sheet_id, manager: 'Bogdana Costan',
        target_v2: 52000, realized_v2: 12948, realized_pct_v2: 24.9,
        forecast_v2: 44715, forecast_pct_v2: 86, report_cutoff: '2026-08-09',
        report_check: { status: 'ok', message: 'OK', target: 52000, realized: 12948, target_diff: 0, realized_diff: 0 },
        v1_check: { status: 'problem', message: 'Realizat V2 -2 lei', target: 52000, realized: 12950, target_diff: 0, realized_diff: -2 },
      })),
    },
  ],
});

describe('Grile run authority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getGrilePilotV2.mockResolvedValue(pilotOverview());
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

  it('keeps the official workflow separate from the five V2 pilot sheets', async () => {
    api.getGrileOverview.mockResolvedValue(overviewWithStore());
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <GrileSubtab initialMonth="2026-08" />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('button', { name: 'Rulează verificare' })).toBeInTheDocument();
    const monthPicker = document.querySelector<HTMLInputElement>('input[type="month"]');
    expect(monthPicker).not.toBeNull();
    fireEvent.change(monthPicker!, { target: { value: '2026-07' } });
    await user.selectOptions(screen.getByLabelText('Stare grilă'), 'ERROR');
    await user.click(screen.getByRole('tab', { name: 'V2 · pilot' }));

    expect(screen.queryByRole('button', { name: 'Rulează verificare' })).not.toBeInTheDocument();
    expect(await screen.findByText('Andrei Stancu')).toBeInTheDocument();
    expect(screen.getByText('Bogdana Costan')).toBeInTheDocument();
    expect(screen.getAllByText('Vs V1 · temporar')).toHaveLength(2);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(5);
    expect(screen.getByRole('link', { name: 'Deschide grila Mobicell Oradea Auchan' })).toHaveAttribute(
      'href',
      'https://docs.google.com/spreadsheets/d/1ZxugdHXXhvPSFyxyOh9bipq11J2N872n7isAxRXMxuM',
    );
    expect(screen.getByRole('link', { name: 'Deschide grila Mobiup Oradea Auchan' })).toHaveAttribute(
      'href',
      'https://docs.google.com/spreadsheets/d/12ejRCcDRNdQqiz38S7BjTKNb-pSrJWW2UNclhFJUiCI',
    );
    expect(screen.getByText(/nu modifică fluxul oficial/i)).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Grila actuală' }));
    expect(await screen.findByRole('button', { name: 'Rulează verificare' })).toBeInTheDocument();
    expect(monthPicker).toHaveValue('2026-07');
    expect(screen.getByLabelText('Stare grilă')).toHaveValue('ERROR');
  });
});
