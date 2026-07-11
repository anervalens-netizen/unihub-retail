import { describe, expect, it } from 'vitest';

import {
  canAccessSalaries,
  canAdministerImports,
  canAccessManagement,
  canAccessPnl,
  canExportReports,
  canWriteBusinessData,
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

describe('P&L owner permission', () => {
  it('allows only the configured owner email', () => {
    expect(canAccessPnl({ email: 'aner.valens@gmail.com' })).toBe(true);
    expect(canAccessPnl({ email: 'other@example.com' })).toBe(false);
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

describe('management and export permissions', () => {
  it.each(['unihub-manager', 'unihub-admin', 'authentik Admins', 'unihub-hr'])('allows %s', (group) => {
    expect(canAccessManagement({ groups: [group] })).toBe(true);
    expect(canExportReports({ groups: [group] })).toBe(true);
  });

  it.each(['unihub-agent', 'unihub-team-lead'])('rejects %s', (group) => {
    expect(canAccessManagement({ groups: [group] })).toBe(false);
    expect(canExportReports({ groups: [group] })).toBe(false);
  });
});

describe('business write permissions', () => {
  it.each(['unihub-manager', 'unihub-admin', 'authentik Admins'])('allows %s', (group) => {
    expect(canWriteBusinessData({ groups: [group] })).toBe(true);
  });

  it.each(['unihub-hr', 'unihub-agent', 'unihub-team-lead'])('rejects %s', (group) => {
    expect(canWriteBusinessData({ groups: [group] })).toBe(false);
  });
});
