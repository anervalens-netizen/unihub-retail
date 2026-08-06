import { beforeEach, describe, expect, it, vi } from 'vitest';

import { generatedGet, generatedPatch, generatedPost } from './client';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

describe('generated Retail client', () => {
  it('resolves path parameters and decodes nullable Decimal fields', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      total_sales: '123.45',
      forecast_sales: null,
    }), { status: 200 }));

    const result = await generatedGet('get_summary_api_dashboard_summary_get', {
      params: { month: '2026-08' },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/dashboard/summary?month=2026-08',
      expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
    );
    expect(result).toEqual({ total_sales: 123.45, forecast_sales: null });
  });

  it('keeps string option values when the schema also contains numeric value fields', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      rows: [{ value: 'Mobiup', label: 'Mobiup' }],
    }), { status: 200 }));

    const result = await generatedGet('get_filter_options_api_filters_options_get', {
      params: { month: '2026-08' },
    });

    expect(result).toEqual({ rows: [{ value: 'Mobiup', label: 'Mobiup' }] });
  });

  it('supports PATCH and Blob responses through the generated route map', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await generatedPatch('update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch', {}, {
      pathParams: { scenario_id: 42 },
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/target-calculator/scenarios/42/rows');

    const blob = new Blob(['xlsx'], { type: 'application/octet-stream' });
    fetchMock.mockResolvedValueOnce({
      status: 200,
      ok: true,
      headers: new Headers(),
      blob: vi.fn().mockResolvedValue(blob),
      text: vi.fn(),
    });
    const result = await generatedGet('export_scenario_api_target_calculator_scenarios__scenario_id__export_get', {
      pathParams: { scenario_id: 42 },
      responseType: 'blob',
    });
    expect(result).toBe(blob);
  });

  it('forwards AbortSignal and uses the generated POST route', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }));
    const controller = new AbortController();
    await generatedPost('get_dashboard_all_batch_api_dashboard_all_batch_post', { queries: [] }, {
      signal: controller.signal,
    });
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ signal: controller.signal }));
  });
});
