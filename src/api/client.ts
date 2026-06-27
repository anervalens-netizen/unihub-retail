type QueryParamValue = string | number | boolean | null | undefined;
type QueryParams = object;
type ResponseType = 'blob' | 'json';

type RequestOptions = {
  headers?: Record<string, string>;
  params?: QueryParams;
  responseType?: ResponseType;
};

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return '/';
}

const API_BASE_URL = resolveApiBaseUrl();

let getAccessTokenFn: (() => string | null) | null = null;
let onUnauthorizedFn: (() => void) | null = null;
let unauthorizedRedirectStarted = false;

export const setAccessTokenProvider = (fn: (() => string | null) | null) => {
  getAccessTokenFn = fn;
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

function getAuthHeaders(existingHeaders: Record<string, string> = {}): Record<string, string> {
  const token = getAccessTokenFn?.();
  if (token) {
    return { ...existingHeaders, Authorization: `Bearer ${token}` };
  }
  return existingHeaders;
}

async function handleResponse(response: Response): Promise<void> {
  if (response.status === 401 && onUnauthorizedFn && !unauthorizedRedirectStarted) {
    unauthorizedRedirectStarted = true;
    onUnauthorizedFn();
  } else if (response.status !== 401) {
    unauthorizedRedirectStarted = false;
  }
  if (!response.ok) throw new Error(`API error: ${response.status}`);
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
    return getAuthHeaders(out);
  }
  return getAuthHeaders({ 'Content-Type': 'application/json', ...headers });
}

export const client = {
  get: async <T = unknown>(
    url: string,
    options?: Omit<RequestOptions, 'headers'>,
  ): Promise<{ data: T }> => {
    const response = await fetch(buildUrl(url, options?.params), {
      method: 'GET',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
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
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
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
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
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
      headers: makeJsonHeaders(data, options?.headers),
      body: makeJsonBody(data),
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
      headers: getAuthHeaders(options?.headers),
    });
    await handleResponse(response);
    return { data: await parseResponse<T>(response, options?.responseType) };
  },
};
