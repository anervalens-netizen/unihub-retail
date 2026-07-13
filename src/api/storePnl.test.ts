import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getPnlAnnual,
  getPnlOverview,
  getPnlPermissions,
  getPnlStores,
} from './storePnl';

afterEach(() => vi.unstubAllGlobals());

describe('getPnlPermissions', () => {
  it.each([true, false])('maps can_view=%s', async (can_view) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ can_view }), { status: 200 })));
    await expect(getPnlPermissions()).resolves.toEqual({ can_view });
  });

  it('uses the server session without exposing an Authorization token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ can_view: true }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getPnlPermissions()).resolves.toEqual({ can_view: true });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/store-pnl/permissions',
      expect.objectContaining({
        credentials: 'same-origin',
      }),
    );
    expect(fetchMock.mock.calls[0]?.[1]?.headers.Authorization).toBeUndefined();
  });

  it('propagates API errors so the caller fails closed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('denied', { status: 403 })));
    await expect(getPnlPermissions()).rejects.toThrow('API error: 403');
  });

  it.each([{}, { can_view: 'true' }, { can_view: 1 }, { can_view: null }, null])(
    'rejects malformed permissions payload %#',
    async (payload) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 })));
      await expect(getPnlPermissions()).rejects.toThrow('Invalid P&L permissions response');
    },
  );
});

describe('P&L scoped data requests', () => {
  it('sends the company and store scope to monthly and annual endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ stores: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ annual: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ stores: [], monthly: [] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await getPnlStores('Mobicell');
    await getPnlAnnual('Mobicell', 'CRFORADEA');
    await getPnlOverview('2026-01', '2026-07', 'Mobicell', 'CRFORADEA');

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/store-pnl/stores?company=Mobicell',
      '/api/store-pnl/annual?company=Mobicell&site_code=CRFORADEA',
      '/api/store-pnl/overview?start_month=2026-01&end_month=2026-07&company=Mobicell&site_code=CRFORADEA',
    ]);
  });

  it('omits empty optional filters', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ annual: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ stores: [], monthly: [] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await getPnlAnnual('', '');
    await getPnlOverview('2026-01', '2026-07', '');

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/store-pnl/annual',
      '/api/store-pnl/overview?start_month=2026-01&end_month=2026-07',
    ]);
  });

  it('qualifies an unmapped source-code scope with its company', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ annual: [] }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getPnlAnnual('', 'LEGACY-CODE', 'Mobicell');

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/store-pnl/annual?site_code=LEGACY-CODE&site_company=Mobicell',
    );
  });
});
