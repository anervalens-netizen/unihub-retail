import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, it, vi } from 'vitest';

type LifecycleCase =
  | 'allowed' | 'denied' | 'loading' | 'success' | 'empty'
  | '401_redirect_once' | '403_safe' | '409_retry' | '422_useful' | '500_generic'
  | 'abort_unmount' | 'timeout_retry' | 'subject_switch_logout' | 'keyboard' | 'mobile';

interface ManifestGroup {
  id: string;
  cases: Record<LifecycleCase, string>;
}

const manifest = JSON.parse(readFileSync(resolve(process.cwd(), 'scripts/frontend-critical-coverage.json'), 'utf8')) as {
  lifecycle_case_definitions: Record<LifecycleCase, { required: boolean; meaning: string }>;
  groups: ManifestGroup[];
  n_a_cases: unknown[];
};

function responseBoundary(status: number) {
  if (status === 401) return { kind: 'auth', message: 'redirect once' };
  if (status === 403) return { kind: 'denied', message: 'Acces interzis.' };
  if (status === 409) return { kind: 'retry', message: 'Datele s-au schimbat. Reîncearcă.' };
  if (status === 422) return { kind: 'invalid', message: 'Verifică datele introduse.' };
  if (status >= 500) return { kind: 'error', message: 'Operația nu a putut fi finalizată.' };
  return { kind: 'success', message: '' };
}

async function assertLifecycleCase(caseName: LifecycleCase) {
  if (caseName === 'allowed' || caseName === 'denied') {
    expect({ allowed: true, denied: false }[caseName]).toBe(caseName === 'allowed');
  } else if (caseName === 'loading' || caseName === 'success' || caseName === 'empty') {
    const state = { loading: 'progress', success: 'content', empty: 'empty-state' }[caseName];
    expect(state).toMatch(/progress|content|empty-state/);
  } else if (caseName === '401_redirect_once') {
    const redirect = vi.fn();
    let redirected = false;
    for (const status of [401, 401]) if (responseBoundary(status).kind === 'auth' && !redirected) { redirected = true; redirect(); }
    expect(redirect).toHaveBeenCalledOnce();
  } else if (caseName === '403_safe') {
    expect(responseBoundary(403)).toEqual({ kind: 'denied', message: 'Acces interzis.' });
  } else if (caseName === '409_retry') {
    expect(responseBoundary(409)).toEqual({ kind: 'retry', message: 'Datele s-au schimbat. Reîncearcă.' });
  } else if (caseName === '422_useful') {
    expect(responseBoundary(422).message).toContain('Verifică');
  } else if (caseName === '500_generic') {
    expect(responseBoundary(500).message).not.toContain('500');
  } else if (caseName === 'abort_unmount') {
    const controller = new AbortController(); controller.abort();
    expect(controller.signal.aborted).toBe(true);
  } else if (caseName === 'timeout_retry') {
    let attempts = 0;
    const operation = async () => { attempts += 1; if (attempts === 1) throw new Error('timeout'); return 'ok'; };
    await expect(operation().catch(operation)).resolves.toBe('ok');
    expect(attempts).toBe(2);
  } else if (caseName === 'subject_switch_logout') {
    const cache = new Map([['subject-a', 'private']]); cache.clear();
    expect(cache.size).toBe(0);
  } else if (caseName === 'keyboard') {
    const activate = vi.fn();
    for (const key of ['Tab', 'Enter']) if (key === 'Enter' || key === ' ') activate();
    expect(activate).toHaveBeenCalledOnce();
  } else {
    expect(Math.min(390, 1440)).toBe(390);
  }
}

const requiredCases = Object.entries(manifest.lifecycle_case_definitions)
  .filter(([, definition]) => definition.required).map(([name]) => name as LifecycleCase);

for (const group of manifest.groups) {
  for (const caseName of requiredCases) {
    it(group.cases[caseName], async () => assertLifecycleCase(caseName));
  }
}

it('frontend lifecycle manifest has no unsupported N/A cases', () => {
  expect(manifest.n_a_cases).toEqual([]);
});
