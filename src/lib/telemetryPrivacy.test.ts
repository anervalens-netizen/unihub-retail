import { describe, expect, it } from 'vitest';

import { scrubTelemetryEvent, stripUrlSecrets } from './telemetryPrivacy';

describe('frontend telemetry privacy boundary', () => {
  it('removes the whole route because path segments can carry stable identities', () => {
    expect(stripUrlSecrets('https://retail.example.invalid/salarii?month=2026-08#row-1'))
      .toBe('https://retail.example.invalid');
    expect(stripUrlSecrets('/api/salarii?agent=private#detail')).toBe('/[REDACTED]');
    expect(stripUrlSecrets(`/salarii/agents/sp1_${'a'.repeat(64)}/history`))
      .toBe('/[REDACTED]');
  });

  it('redacts headers, bodies, identity, money and all free-text error fields', () => {
    const event = scrubTelemetryEvent({
      request: {
        url: 'https://retail.example.invalid/api/salarii?agent=private',
        headers: { Authorization: 'Bearer private', Cookie: 'private' },
        data: { employee_name: 'private', salary: '1234.56' },
      },
      exception: {
        values: [{ type: 'ApiError', value: 'private server detail', detail: 'private API detail' }],
      },
      breadcrumbs: [{ category: 'fetch', message: 'private breadcrumb', data: { body: 'private' } }],
      transaction: `/salarii/agents/sp1_${'a'.repeat(64)}/history`,
      spans: [{ description: `/api/salarii/agents/sp1_${'b'.repeat(64)}` }],
      user: { email: 'private@example.invalid', username: 'private' },
      contexts: { response: { body: { cnp: 'private', salariu: '1234.56' } } },
      cnp: 'private',
    });

    expect(event.request).toEqual({
      url: 'https://retail.example.invalid',
      headers: '[REDACTED]',
      data: '[REDACTED]',
    });
    expect(event.exception).toEqual({
      values: [{ type: 'ApiError', value: '[REDACTED]', detail: '[REDACTED]' }],
    });
    expect(event.breadcrumbs).toEqual([
      { category: 'fetch', message: '[REDACTED]', data: '[REDACTED]' },
    ]);
    expect(event.transaction).toBe('/[REDACTED]');
    expect(event.spans).toEqual([{ description: '[REDACTED]' }]);
    expect(event.user).toEqual({ email: '[REDACTED]', username: '[REDACTED]' });
    expect(event.contexts).toEqual({ response: { body: '[REDACTED]' } });
    expect(event.cnp).toBe('[REDACTED]');
  });

  it('bounds recursive attacker-controlled structures without mutating input', () => {
    const cycle: Record<string, unknown> = {};
    cycle.self = cycle;
    const input = {
      message: 'private',
      tags: { release: 'abc' },
      list: Array(150).fill('safe'),
      cycle,
    };
    const result = scrubTelemetryEvent(input);

    expect(result).not.toBe(input);
    expect(result.message).toBe('[REDACTED]');
    expect(result.tags).toEqual({ release: 'abc' });
    expect(result.list).toHaveLength(64);
    expect(result.cycle).toEqual({ self: '[CIRCULAR]' });
    expect(input.message).toBe('private');
  });
});
