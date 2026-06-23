import { describe, expect, it } from 'vitest';

import { sanitizeActiveTab } from './navigationAccess';

describe('role-aware navigation', () => {
  it.each(['hub', 'focus', 'agents', 'settings'])(
    'keeps public authenticated tab %s',
    (tab) => {
      expect(sanitizeActiveTab(tab, false)).toBe(tab);
    },
  );

  it('keeps management for authorized users', () => {
    expect(sanitizeActiveTab('management', true)).toBe('management');
  });

  it('redirects unauthorized persisted management state to hub', () => {
    expect(sanitizeActiveTab('management', false)).toBe('hub');
  });

  it.each([null, undefined, '', 'unknown'])(
    'falls back to hub for invalid stored value %j',
    (value) => {
      expect(sanitizeActiveTab(value, true)).toBe('hub');
    },
  );
});
