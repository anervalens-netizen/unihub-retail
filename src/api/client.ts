import * as Sentry from '@sentry/react';

type QueryParamValue = string | number | boolean | null | undefined;
type QueryParams = object;
type ResponseType = 'blob' | 'json';

type RequestOptions = {
  headers?: Record<string, string>;
  params?: QueryParams;
  responseType?: ResponseType;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export const API_READ_TIMEOUT_MS = 15_000;
export const API_MUTATION_TIMEOUT_MS = 30_000;
export const API_UPLOAD_TIMEOUT_MS = 120_000;

export function requestSignal(
  callerSignal: AbortSignal | undefined,
  timeoutMs: number,
): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  return callerSignal
    ? AbortSignal.any([callerSignal, timeoutSignal])
    : timeoutSignal;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: unknown;

  constructor(status: number, detail: string, body: unknown) {
    super(detail ? `API error: ${status} - ${detail}` : `API error: ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

const USER_ACTIONABLE_ERROR_STATUSES = new Set([400, 403, 404, 409, 422]);

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 401) {
    return 'Sesiunea a expirat. Vei fi redirectionat catre autentificare.';
  }
  if (!USER_ACTIONABLE_ERROR_STATUSES.has(error.status)) return fallback;
  const detail = error.detail.trim();
  return detail || fallback;
}

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return '/';
}

const API_BASE_URL = resolveApiBaseUrl();

let getCsrfTokenFn: (() => string | null) | null = null;
let onUnauthorizedFn: (() => void) | null = null;
let unauthorizedRedirectStarted = false;

export const setCsrfTokenProvider = (fn: (() => string | null) | null) => {
  getCsrfTokenFn = fn;
  unauthorizedRedirectStarted = false;
};

export const setUnauthorizedHandler = (fn: (() => void) | null) => {
  onUnauthorizedFn = fn;
};

function buildUrl(url: string, params?: QueryParams): string {
  let fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
  if (!params) return fullUrl;

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]: [string, unknown]) => {
    if (value !== undefined && value !== null) {
      searchParams.append(key, String(value as QueryParamValue));
    }
  });
  const qs = searchParams.toString();
  if (qs) {
    fullUrl += fullUrl.includes('?') ? `&${qs}` : `?${qs}`;
  }
  return fullUrl;
}

function hasHeader(headers: Record<string, string>, name: string): boolean {
  const normalizedName = name.toLowerCase();
  return Object.keys(headers).some((key) => key.toLowerCase() === normalizedName);
}

function getSessionHeaders(existingHeaders: Record<string, string> = {}, csrf = false): Record<string, string> {
  if (csrf && !hasHeader(existingHeaders, 'x-csrf-token')) {
    const token = getCsrfTokenFn?.();
    if (token) return { ...existingHeaders, 'X-CSRF-Token': token };
  }
  return existingHeaders;
}

async function handleResponse(response: Response): Promise<void> {
  const requestId = response.headers.get('x-request-id');
  if (requestId) {
    Sentry.getActiveSpan()?.setAttribute('server.request_id', requestId);
  }
  if (response.status === 401 && onUnauthorizedFn && !unauthorizedRedirectStarted) {
    unauthorizedRedirectStarted = true;
    onUnauthorizedFn();
  } else if (response.status !== 401) {
    unauthorizedRedirectStarted = false;
  }
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    let detail = text;
    let body: unknown = text || null;
    if (text) {
      try {
        body = JSON.parse(text) as unknown;
        const parsedDetail =
          body && typeof body === 'object' && 'detail' in body
            ? (body as { detail?: unknown }).detail
            : undefined;
        if (typeof parsedDetail === 'string') {
          detail = parsedDetail;
        } else if (Array.isArray(parsedDetail) && parsedDetail.length > 0) {
          detail = parsedDetail
            .map((item) => {
              if (typeof item === 'string') return item;
              if (item && typeof item === 'object' && 'msg' in item) return String(item.msg);
              return '';
            })
            .filter(Boolean)
            .join('; ');
        }
      } catch {
        detail = text;
      }
    }
    throw new ApiError(response.status, detail, body);
  }
}

async function parseResponse<T>(response: Response, responseType: ResponseType = 'json'): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  if (responseType === 'blob') {
    return (await response.blob()) as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

function makeJsonBody(data: unknown): BodyInit | undefined {
  if (data === undefined || data === null) return undefined;
  if (data instanceof FormData) return data;
  return JSON.stringify(data);
}

function makeJsonHeaders(data: unknown, headers?: Record<string, string>): Record<string, string> {
  if (data instanceof FormData) {
    const out = { ...headers };
    delete out['Content-Type'];
    return getSessionHeaders(out, true);
  }
  return getSessionHeaders({ 'Content-Type': 'application/json', ...headers }, true);
}

export const client = {
  get: async <T = unknown>(
    url: string,
    options?: RequestOptions,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'GET',
      credentials: 'same-origin',
      headers: getSessionHeaders({ 'Content-Type': 'application/json', ...options?.headers }),
      signal: requestSignal(options?.signal, options?.timeoutMs ?? API_READ_TIMEOUT_MS),
    });

    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },

  post: async <T = unknown>(
    url: string,
    data?: unknown,
    options?: RequestOptions,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'POST',
      credentials: 'same-origin',
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
      signal: requestSignal(
        options?.signal,
        options?.timeoutMs ?? (data instanceof FormData ? API_UPLOAD_TIMEOUT_MS : API_MUTATION_TIMEOUT_MS),
      ),
    });

    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },

  put: async <T = unknown>(
    url: string,
    data?: unknown,
    options?: RequestOptions,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'PUT',
      credentials: 'same-origin',
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
      signal: requestSignal(options?.signal, options?.timeoutMs ?? API_MUTATION_TIMEOUT_MS),
    });
    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },

  patch: async <T = unknown>(
    url: string,
    data?: unknown,
    options?: RequestOptions,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
      signal: requestSignal(options?.signal, options?.timeoutMs ?? API_MUTATION_TIMEOUT_MS),
    });
    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },

  delete: async <T = unknown>(
    url: string,
    options?: RequestOptions,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: getSessionHeaders(options?.headers, true),
      signal: requestSignal(options?.signal, options?.timeoutMs ?? API_MUTATION_TIMEOUT_MS),
    });
    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },
};
