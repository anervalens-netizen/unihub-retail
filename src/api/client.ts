function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return '/';
}

const API_BASE_URL = resolveApiBaseUrl();

let getAccessTokenFn: (() => string | null) | null = null;

export const setAccessTokenProvider = (fn: () => string | null) => {
  getAccessTokenFn = fn;
};

function getAuthHeaders(existingHeaders: Record<string, string> = {}): Record<string, string> {
  const token = getAccessTokenFn?.();
  if (token) {
    return { ...existingHeaders, Authorization: `Bearer ${token}` };
  }
  return existingHeaders;
}

export const client = {
  get: async <T = any>(url: string, options?: { params?: Record<string, any>; responseType?: 'blob' | 'json' }): Promise<{ data: T }> => {
    let fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
    
    if (options?.params) {
      const searchParams = new URLSearchParams();
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      const qs = searchParams.toString();
      if (qs) {
        fullUrl += fullUrl.includes('?') ? `&${qs}` : `?${qs}`;
      }
    }

    const headers = getAuthHeaders({ 'Content-Type': 'application/json' });

    const response = await fetch(fullUrl, {
      method: 'GET',
      headers,
    });

    if (!response.ok) throw new Error(`API error: ${response.status}`);

    if (options?.responseType === 'blob') {
      const blob = await response.blob();
      return { data: blob as unknown as T };
    }

    const data = await response.json();
    return { data };
  },

  post: async <T = any>(url: string, data?: any, options?: { headers?: Record<string, string>; params?: Record<string, any> }): Promise<{ data: T }> => {
    let fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
    
    if (options?.params) {
      const searchParams = new URLSearchParams();
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      const qs = searchParams.toString();
      if (qs) {
        fullUrl += fullUrl.includes('?') ? `&${qs}` : `?${qs}`;
      }
    }
    
    // Auto-detect FormData so we don't set Content-Type to JSON
    const isFormData = data instanceof FormData;
    let headers: Record<string, string> = { ...options?.headers };
    if (!isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    headers = getAuthHeaders(headers);

    const response = await fetch(fullUrl, {
      method: 'POST',
      headers,
      body: isFormData ? data : (data ? JSON.stringify(data) : undefined),
    });

    if (!response.ok) throw new Error(`API error: ${response.status}`);
    const responseData = await response.json();
    return { data: responseData };
  },

  put: async <T = any>(url: string, data?: any): Promise<{ data: T }> => {
    const fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
    const headers = getAuthHeaders({ 'Content-Type': 'application/json' });
    const response = await fetch(fullUrl, {
      method: 'PUT',
      headers,
      body: data ? JSON.stringify(data) : undefined,
    });
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    const responseData = await response.json();
    return { data: responseData };
  },

  patch: async <T = any>(url: string, data?: any): Promise<{ data: T }> => {
    const fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
    const headers = getAuthHeaders({ 'Content-Type': 'application/json' });
    const response = await fetch(fullUrl, {
      method: 'PATCH',
      headers,
      body: data ? JSON.stringify(data) : undefined,
    });
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    const responseData = await response.json();
    return { data: responseData };
  },

  delete: async <T = any>(url: string): Promise<{ data: T }> => {
    const fullUrl = API_BASE_URL === '/' ? url : `${API_BASE_URL}${url}`;
    const headers = getAuthHeaders();
    const response = await fetch(fullUrl, {
      method: 'DELETE',
      headers,
    });
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    const responseData = await response.json();
    return { data: responseData };
  }
};
