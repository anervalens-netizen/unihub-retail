import axios from 'axios';

export interface ErrorLogEntry {
  id: number;
  ts: string;
  source: 'backend' | 'frontend';
  level: 'error' | 'warning';
  message: string;
  traceback: string | null;
  path: string | null;
  user_id: number | null;
  extra: string | null;
  seen: boolean;
}

export interface UnseenCountResponse {
  count: number;
}

export async function postFrontendError(payload: {
  message: string;
  traceback?: string | null;
  path?: string | null;
  user_id?: number | null;
  extra?: Record<string, unknown> | null;
}): Promise<void> {
  try {
    await axios.post('/api/errors', payload, { timeout: 3000 });
  } catch {
    // fire-and-forget — nu bloca UX niciodată
  }
}

export async function getUnseenCount(token: string): Promise<number> {
  const res = await axios.get<UnseenCountResponse>(
    '/api/admin/error-logs/unseen-count',
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return res.data.count;
}

export async function markAllSeen(token: string): Promise<void> {
  await axios.post(
    '/api/admin/error-logs/mark-seen',
    {},
    { headers: { Authorization: `Bearer ${token}` } }
  );
}

export async function getErrorLogs(
  token: string,
  params: {
    source?: string;
    level?: string;
    seen?: boolean;
    from_date?: string;
    to_date?: string;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ErrorLogEntry[]> {
  const res = await axios.get<ErrorLogEntry[]>('/api/admin/error-logs', {
    headers: { Authorization: `Bearer ${token}` },
    params,
  });
  return res.data;
}
