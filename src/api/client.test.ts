import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { client, setAccessTokenProvider, setUnauthorizedHandler } from './client';

const mockFetch = vi.fn();
type FetchCall = [string, { method: string; headers: Record<string, string>; body?: BodyInit | string }];

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  setAccessTokenProvider(null as any);
  setUnauthorizedHandler(null as any);
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

  it('injects Authorization header when token provider is set', async () => {
    setAccessTokenProvider(() => 'test-token-123');
    mockFetch.mockResolvedValueOnce(okResponse({}));
    await client.get('/api/data');
    const [, opts] = fetchCall();
    expect(opts.headers.Authorization).toBe('Bearer test-token-123');
  });

  it('does not include Authorization when no token provider', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}));
    await client.get('/api/data');
    const [, opts] = fetchCall();
    expect(opts.headers.Authorization).toBeUndefined();
  });

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 500 }));
    await expect(client.get('/api/fail')).rejects.toThrow('API error: 500');
  });
});

describe('client.post', () => {
  it('sends JSON body', async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ id: 1 }));
    const { data } = await client.post('/api/items', { name: 'test' });
    const [url, opts] = latestFetchCall();
    expect(url).toBe('/api/items');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBe(JSON.stringify({ name: 'test' }));
    expect(data).toEqual({ id: 1 });
  });

  it('handles FormData by not forcing Content-Type', async () => {
    const fd = new FormData();
    fd.append('file', 'content');
    mockFetch.mockResolvedValueOnce(okResponse({ ok: true }));
    await client.post('/api/upload', fd);
    const [, opts] = latestFetchCall();
    expect(opts.body).toBe(fd);
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
});
