import {describe, expect, it} from 'vitest';

import {PWA_NAVIGATION_DENYLIST} from './pwaNavigation';

const isDenied = (path: string) =>
  PWA_NAVIGATION_DENYLIST.some((pattern) => pattern.test(path));

describe('PWA navigation fallback', () => {
  it.each([
    '/auth/session',
    '/auth/session/login',
    '/auth/callback',
    '/api/dashboard/all',
    '/salarii/records',
    '/docs',
    '/docs/oauth2-redirect',
    '/health',
    '/livez',
    '/readyz',
    '/metrics',
    '/openapi.json',
  ])('keeps the server route %s outside the SPA fallback', (path) => {
    expect(isDenied(path)).toBe(true);
  });

  it.each([
    '/',
    '/hub',
    '/agenti',
    '/management',
    '/management/pnl',
  ])('keeps the client route %s eligible for the SPA fallback', (path) => {
    expect(isDenied(path)).toBe(false);
  });

  it('does not deny lookalike client routes', () => {
    expect(isDenied('/authentication-help')).toBe(false);
    expect(isDenied('/apiary')).toBe(false);
    expect(isDenied('/healthy-stores')).toBe(false);
  });
});
