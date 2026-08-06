// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import type { TargetCalculatorContext, TargetScenario } from './api';

const api = vi.hoisted(() => ({
  calculateTargetScenario: vi.fn(),
  downloadTargetScenario: vi.fn(),
  fetchTargetCalculatorContext: vi.fn(),
  fetchTargetScenario: vi.fn(),
  fetchTargetScenarios: vi.fn(),
  finalizeTargetScenario: vi.fn(),
  saveTargetFinalValues: vi.fn(),
}));

vi.mock('./api', () => api);

import { TargetCalculatorPage } from './TargetCalculatorPage';

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
      site_code: 'S1',
      locatie: 'Magazin test',
      firma: 'Mobiup',
      regional: 'Nord',
      asm: 'Nord',
      calculated_weight: 1,
      normalized_weight: 1,
      floor_target: 100,
      proposed_target: 1000,
      final_target: 1000,
      note: null,
      history: [],
      calculation_details: {},
    }],
    ...overrides,
  } as unknown as TargetScenario;
}

function installMediaQuery(matches = false) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: () => ({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
}

describe('TargetCalculatorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installMediaQuery();
    vi.stubGlobal('confirm', vi.fn(() => true));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    api.fetchTargetCalculatorContext.mockResolvedValue(context);
    api.fetchTargetScenarios.mockResolvedValue([]);
    api.fetchTargetScenario.mockResolvedValue(scenario());
    api.saveTargetFinalValues.mockResolvedValue(scenario());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading, applies backend defaults, and sends the calculation payload through the feature owner', async () => {
    let resolveContext: ((value: TargetCalculatorContext) => void) | undefined;
    let resolveScenarios: ((value: TargetScenario[]) => void) | undefined;
    api.fetchTargetCalculatorContext.mockImplementationOnce(() => new Promise((resolve) => {
      resolveContext = resolve;
    }));
    api.fetchTargetScenarios.mockImplementationOnce(() => new Promise((resolve) => {
      resolveScenarios = resolve;
    }));
    api.calculateTargetScenario.mockReturnValue(new Promise(() => undefined));

    render(<TargetCalculatorPage />);

    expect(screen.getByText('Se incarca calculatorul de target...')).toBeInTheDocument();

    resolveContext?.(context);
    resolveScenarios?.([]);

    const targetMonth = await screen.findByLabelText('Luna target');
    expect(targetMonth).toHaveValue('2026-08');
    expect(screen.getByLabelText('Target total (RON)')).toHaveValue(1000);
    expect(screen.getByLabelText('Prag minim (RON)')).toHaveValue(100);

    fireEvent.click(screen.getByRole('button', { name: 'Calculeaza propunerea' }));

    await waitFor(() => expect(api.calculateTargetScenario).toHaveBeenCalledWith({
      target_month: '2026-08',
      total_target: 1000,
      min_floor: 100,
      previous_month_floor_pct: 0,
      previous_month_cap_pct: 1.7,
      seasonality_years: 1,
      expected_revision: undefined,
    }));
  });

  it('exposes a retry from the owner after a 409 while saving a manager value', async () => {
    api.fetchTargetScenarios.mockResolvedValue([{ id: 7, target_month: '2026-08' }]);
    api.saveTargetFinalValues.mockRejectedValue(new ApiError(409, 'revizie noua', null));

    render(<TargetCalculatorPage />);

    await screen.findByRole('button', { name: 'Salveaza acum' });
    const managerTarget = screen.getAllByPlaceholderText('Completeaza')[0];
    if (!managerTarget) throw new Error('Lipsește câmpul pentru propunerea managerului.');
    fireEvent.change(managerTarget, { target: { value: '950' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salveaza acum' }));

    const retry = await screen.findByRole('button', { name: 'Reîncearcă salvarea' });
    expect(screen.getByRole('alert')).toHaveTextContent('revizie noua');
    expect(api.saveTargetFinalValues).toHaveBeenCalledWith(7, {
      expected_revision: 3,
      rows: [{ site_code: 'S1', final_target: 950, note: null }],
    });

    fireEvent.click(retry);
    await waitFor(() => expect(api.saveTargetFinalValues).toHaveBeenCalledTimes(2));
  });
});
