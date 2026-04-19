import axios from 'axios';

export interface ErrorLogEntry {
  id: number;
  ts: string;
  source: 'backend' | 'frontend';
  level: 'error' | 'warning';
  message: string;
  traceback: string | null;
  path: string | null;
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
  extra?: Record<string, unknown> | null;
}): Promise<void> {
  try {
    await axios.post('/api/errors', payload, { timeout: 3000 });
  } catch {
    // fire-and-forget — nu bloca UX niciodată
  }
}

export async function getUnseenCount(): Promise<number> {
  const res = await axios.get<UnseenCountResponse>('/api/admin/error-logs/unseen-count');
  return res.data.count;
}

export async function markAllSeen(): Promise<void> {
  await axios.post('/api/admin/error-logs/mark-seen', {});
}

export async function getErrorLogs(
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
  const res = await axios.get<ErrorLogEntry[]>('/api/admin/error-logs', { params });
  return res.data;
}
