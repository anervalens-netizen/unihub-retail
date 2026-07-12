import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const authSource = readFileSync(new URL('./AuthContext.tsx', import.meta.url), 'utf8');
const clientSource = readFileSync(new URL('../api/client.ts', import.meta.url), 'utf8');
const e2eSource = readFileSync(new URL('../../e2e/helpers.ts', import.meta.url), 'utf8');

describe('H-06 browser session boundary', () => {
  it('keeps OIDC tokens and refresh machinery out of browser code', () => {
    for (const forbidden of [
      'oidc-client-ts',
      'UserManager',
      'WebStorageStateStore',
      'access_token',
      'refresh_token',
      'signinSilent',
      'localStorage',
    ]) {
      expect(authSource).not.toContain(forbidden);
    }
  });

  it('uses same-origin cookies and CSRF instead of bearer injection', () => {
    expect(clientSource).toContain("credentials: 'same-origin'");
    expect(clientSource).toContain("'X-CSRF-Token'");
    expect(clientSource).not.toContain('Bearer ');
    expect(clientSource).not.toContain('getAccessToken');
    expect(e2eSource).not.toContain('access_token');
    expect(e2eSource).not.toContain('Bearer');
  });
});
