// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../../api/client';
import type { TargetCalculatorContext, TargetScenario } from '../api';

const api = vi.hoisted(() => ({
  calculateTargetScenario: vi.fn(),
  downloadTargetScenario: vi.fn(),
  fetchTargetCalculatorContext: vi.fn(),
  fetchTargetScenario: vi.fn(),
  fetchTargetScenarios: vi.fn(),
  finalizeTargetScenario: vi.fn(),
  saveTargetFinalValues: vi.fn(),
}));

vi.mock('../api', () => api);

import { useTargetScenario } from './useTargetScenario';

const context = {
  active_store_count: 1,
  can_finalize: true,
  default_min_floor: 100,
  default_previous_month_cap_pct: 1.7,
  default_previous_month_floor_pct: 0,
  default_seasonality_years: 1,
  latest_sales_month: '2026-07',
  regionals: ['Nord'],
  suggested_cohort_month: '2026-07',
  suggested_target_month: '2026-08',
  suggested_total_target: 1000,
} as TargetCalculatorContext;

function scenario(overrides: Record<string, unknown> = {}): TargetScenario {
  return {
    id: 7,
    status: 'draft',
    revision: 3,
    target_month: '2026-08',
    cohort_month: '2026-07',
    total_target: 1000,
    proposed_total: 1000,
    final_total: 1000,
    remaining_difference: 0,
    pending_final_count: 0,
    manual_adjustments_count: 1,
    store_count: 1,
    min_floor: 100,
    previous_month_floor_pct: 0,
    floor_limited_count: 0,
    calculation_method: 'v2',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    calculation_params: { seasonality_years: 1 },
    regional_summary: [],
    source_months: [],
    warnings: [],
    rows: [{
      site_code: 'S1', locatie: 'Magazin test', firma: 'Mobiup', regional: 'Nord', asm: 'Nord',
      calculated_weight: 1, normalized_weight: 1, floor_target: 100, proposed_target: 1000,
      final_target: 1000, note: null, history: [], calculation_details: {},
    }],
    ...overrides,
  } as unknown as TargetScenario;
}

describe('useTargetScenario', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    });
    vi.stubGlobal('confirm', vi.fn(() => true));
    api.fetchTargetCalculatorContext.mockResolvedValue(context);
    api.fetchTargetScenarios.mockResolvedValue([]);
    api.fetchTargetScenario.mockResolvedValue(scenario());
    api.calculateTargetScenario.mockResolvedValue(scenario());
    api.saveTargetFinalValues.mockResolvedValue(scenario());
    api.finalizeTargetScenario.mockResolvedValue(scenario({ status: 'finalized' }));
  });

  it('initializes defaults and sends the canonical calculation payload', async () => {
    const { result } = renderHook(() => useTargetScenario());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.targetMonth).toBe('2026-08');
    expect(result.current.totalTarget).toBe('1000');
    expect(result.current.minFloor).toBe('100');

    await act(async () => { await result.current.handleCalculate(); });

    expect(api.calculateTargetScenario).toHaveBeenCalledWith({
      target_month: '2026-08', total_target: 1000, min_floor: 100,
      previous_month_floor_pct: 0, previous_month_cap_pct: 1.7,
      seasonality_years: 1, expected_revision: undefined,
    });
  });

  it('applies a multi-year backend default when no scenario or manual choice exists', async () => {
    api.fetchTargetCalculatorContext.mockResolvedValue({
      ...context,
      default_seasonality_years: 3,
    });
    const { result } = renderHook(() => useTargetScenario());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.seasonalityMode).toBe('multi');
  });

  it('preserves a manual seasonality choice across a context refetch and sends it', async () => {
    api.fetchTargetCalculatorContext.mockResolvedValue({
      ...context,
      default_seasonality_years: 3,
    });
    const { result } = renderHook(() => useTargetScenario());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.seasonalityMode).toBe('multi');

    act(() => result.current.selectSeasonalityMode('single'));
    await act(async () => { await result.current.loadInitial(); });
    expect(result.current.seasonalityMode).toBe('single');

    await act(async () => { await result.current.handleCalculate(); });
    expect(api.calculateTargetScenario).toHaveBeenLastCalledWith(
      expect.objectContaining({ seasonality_years: 1 }),
    );
  });

  it('prefers the loaded scenario seasonality over the backend default', async () => {
    api.fetchTargetCalculatorContext.mockResolvedValue({
      ...context,
      default_seasonality_years: 3,
    });
    api.fetchTargetScenarios.mockResolvedValue([{ id: 7, target_month: '2026-08' }]);
    api.fetchTargetScenario.mockResolvedValue(scenario({
      calculation_params: { seasonality_years: 1 },
    }));
    const { result } = renderHook(() => useTargetScenario());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.seasonalityMode).toBe('single');
  });

  it('keeps local edits and exposes retry after a 409 save conflict', async () => {
    api.fetchTargetScenarios.mockResolvedValue([{ id: 7, target_month: '2026-08' }]);
    api.saveTargetFinalValues.mockRejectedValue(new ApiError(409, 'revizie noua', null));
    const { result } = renderHook(() => useTargetScenario());

    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.updateRow('S1', 'final_target', 950));
    await act(async () => { await result.current.handleSave(); });

    expect(api.saveTargetFinalValues).toHaveBeenCalledWith(7, {
      expected_revision: 3,
      rows: [{ site_code: 'S1', final_target: 950, note: null }],
    });
    expect(result.current.conflictRetryAvailable).toBe(true);
    expect(result.current.error).toContain('revizie noua');
  });

  it('finalizes only after fetching the latest revision', async () => {
    api.fetchTargetScenarios.mockResolvedValue([{ id: 7, target_month: '2026-08' }]);
    const { result } = renderHook(() => useTargetScenario());

    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.handleFinalize(); });

    expect(api.fetchTargetScenario).toHaveBeenCalledWith(7);
    expect(api.finalizeTargetScenario).toHaveBeenCalledWith(7, {
      expected_revision: 3,
    });
  });
});
