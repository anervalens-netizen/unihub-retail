import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { client, setCsrfTokenProvider, setUnauthorizedHandler } from './client';

const mockFetch = vi.fn();
type FetchCall = [string, { method: string; headers: Record<string, string>; body?: BodyInit | string }];

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  setCsrfTokenProvider(null);
  setUnauthorizedHandler(null);
});

afterEach(() => {
  vi.restoreAllMocks();
});

function okResponse(data: any) {
  return new Response(JSON.stringify(data), { status: 200 });
}

function fetchCall(index = 0): FetchCall {
  const call = mockFetch.mock.calls[index] as FetchCall | undefined;
  expect(call).toBeDefined();
  return call as FetchCall;
}

function latestFetchCall(): FetchCall {
  return fetchCall(mockFetch.mock.calls.length - 1);
}

describe('client.get', () => {
  it('makes a GET request to the given URL', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ status: 'ok' }));
    const { data } = await client.get('/api/health');
    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, opts] = fetchCall();
    expect(url).toBe('/api/health');
    expect(opts.method).toBe('GET');
    expect(data).toEqual({ status: 'ok' });
  });

  it('appends query params to URL', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}));
    await client.get('/api/data', { params: { month: '2026-05', firma: 'MobiCell' } });
    const [url] = fetchCall();
    expect(url).toContain('month=2026-05');
    expect(url).toContain('firma=MobiCell');
  });

  it('skips undefined and null params', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}));
    await client.get('/api/data', { params: { month: '2026-05', firma: undefined, rm: null } });
    const [url] = fetchCall();
    expect(url).toContain('month=2026-05');
    expect(url).not.toContain('firma');
    expect(url).not.toContain('rm');
  });

  it('uses same-origin credentials without an Authorization header', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}));
    await client.get('/api/data');
    const [, opts] = fetchCall();
    expect(opts.headers.Authorization).toBeUndefined();
    expect((opts as RequestInit).credentials).toBe('same-origin');
  });

  it('preserves an explicit integration Authorization header', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}));

    await client.get('/api/data', {
      headers: { Authorization: 'Bearer current-session-token' },
    });

    const [, opts] = fetchCall();
    expect(opts.headers.Authorization).toBe('Bearer current-session-token');
  });

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 500 }));
    await expect(client.get('/api/fail')).rejects.toThrow('API error: 500');
  });

  it('returns undefined for empty 204 responses', async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const { data } = await client.get<void>('/api/no-content');
    expect(data).toBeUndefined();
  });
});

describe('client.post', () => {
  it('sends JSON body', async () => {
    setCsrfTokenProvider(() => 'synthetic-csrf-token');
    mockFetch.mockResolvedValueOnce(okResponse({ id: 1 }));
    const { data } = await client.post('/api/items', { name: 'test' });
    const [url, opts] = latestFetchCall();
    expect(url).toBe('/api/items');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBe(JSON.stringify({ name: 'test' }));
    expect(opts.headers['X-CSRF-Token']).toBe('synthetic-csrf-token');
    expect(data).toEqual({ id: 1 });
  });

  it('handles FormData by not forcing Content-Type', async () => {
    setCsrfTokenProvider(() => 'synthetic-csrf-token');
    const fd = new FormData();
    fd.append('file', 'content');
    mockFetch.mockResolvedValueOnce(okResponse({ ok: true }));
    await client.post('/api/upload', fd);
    const [, opts] = latestFetchCall();
    expect(opts.body).toBe(fd);
    expect(opts.headers['Content-Type']).toBeUndefined();
    expect(opts.headers['X-CSRF-Token']).toBe('synthetic-csrf-token');
  });
});

describe('client verbs', () => {
  it('supports query params on PATCH', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ ok: true }));
    await client.patch('/api/items/1', { name: 'x' }, { params: { revision: 4 } });
    const [url, opts] = latestFetchCall();
    expect(url).toBe('/api/items/1?revision=4');
    expect(opts.method).toBe('PATCH');
  });

  it('supports query params on DELETE', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ ok: true }));
    await client.delete('/api/items/1', { params: { force: true } });
    const [url, opts] = latestFetchCall();
    expect(url).toBe('/api/items/1?force=true');
    expect(opts.method).toBe('DELETE');
  });
});

describe('unauthorized handler', () => {
  it('calls handler on 401 response', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 401 }));
    await expect(client.get('/api/protected')).rejects.toThrow('API error: 401');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('allows a new 401 redirect after a successful response', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(okResponse({ ok: true }))
      .mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await expect(client.get('/api/protected')).rejects.toThrow('API error: 401');
    await client.get('/api/health');
    await expect(client.get('/api/protected-again')).rejects.toThrow('API error: 401');

    expect(handler).toHaveBeenCalledTimes(2);
  });
});
