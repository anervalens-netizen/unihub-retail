import { describe, expect, it } from 'vitest';

import {
  canAccessSalaries,
  canAdministerImports,
  oidcGroups,
} from './permissions';

describe('salary permissions', () => {
  it.each([
    'unihub-manager',
    'unihub-admin',
    'authentik Admins',
    'unihub-hr',
  ])('allows %s', (group) => {
    expect(canAccessSalaries({ groups: [group] })).toBe(true);
  });

  it.each([
    undefined,
    [],
    ['unihub-agent'],
    ['unihub-team-lead'],
    ['manager'],
  ])('rejects non-salary groups: %j', (groups) => {
    expect(canAccessSalaries({ groups })).toBe(false);
  });

  it('normalizes a single group claim', () => {
    expect(oidcGroups({ groups: 'unihub-manager' })).toEqual([
      'unihub-manager',
    ]);
  });

  it('falls back to the access-token groups claim', () => {
    const payload = btoa(JSON.stringify({ groups: ['unihub-manager'] }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    const token = `header.${payload}.signature`;

    expect(canAccessSalaries({}, token)).toBe(true);
  });
});

describe('import permissions', () => {
  it.each(['unihub-admin', 'authentik Admins'])('allows %s', (group) => {
    expect(canAdministerImports({ groups: [group] })).toBe(true);
  });

  it.each([
    'unihub-manager',
    'unihub-hr',
    'unihub-agent',
    'unihub-team-lead',
  ])('rejects %s', (group) => {
    expect(canAdministerImports({ groups: [group] })).toBe(false);
  });
});
