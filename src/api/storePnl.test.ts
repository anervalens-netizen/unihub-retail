import { afterEach, describe, expect, it, vi } from 'vitest';

import { getPnlPermissions } from './storePnl';

afterEach(() => vi.unstubAllGlobals());

describe('getPnlPermissions', () => {
  it.each([true, false])('maps can_view=%s', async (can_view) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ can_view }), { status: 200 })));
    await expect(getPnlPermissions()).resolves.toEqual({ can_view });
  });

  it('uses the explicitly supplied token during the auth bootstrap race', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ can_view: true }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getPnlPermissions('bootstrap-access-token')).resolves.toEqual({ can_view: true });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/store-pnl/permissions',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer bootstrap-access-token' }),
      }),
    );
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
