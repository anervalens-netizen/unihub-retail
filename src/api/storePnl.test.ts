import { afterEach, describe, expect, it, vi } from 'vitest';

import { getPnlPermissions } from './storePnl';

afterEach(() => vi.unstubAllGlobals());

describe('getPnlPermissions', () => {
  it.each([true, false])('maps can_view=%s', async (can_view) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ can_view }), { status: 200 })));
    await expect(getPnlPermissions()).resolves.toEqual({ can_view });
  });

  it('propagates API errors so the caller fails closed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('denied', { status: 403 })));
    await expect(getPnlPermissions()).rejects.toThrow('API error: 403');
  });
});
