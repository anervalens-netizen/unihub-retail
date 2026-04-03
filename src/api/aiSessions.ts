import { client } from './client';

export interface AiAttachment {
  kind: 'image' | 'document';
  path: string;
  mime_type: string;
  name: string;
  size: number;
}

export interface AiSessionSummary {
  id: string;
  title: string;
  preview: string;
  updated_at: string;
  is_active: boolean;
}

export interface AiSessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface AiSessionDetail {
  session: {
    id: string;
    title: string;
  };
  messages: AiSessionMessage[];
}

export interface AiSessionList {
  active_session_id: string;
  sessions: AiSessionSummary[];
}

export function getAiDeviceId(): string {
  const key = 'unihub_ai_device_id';
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const next = crypto.randomUUID();
  localStorage.setItem(key, next);
  return next;
}

export async function listAiSessions(deviceId: string): Promise<AiSessionList> {
  const { data } = await client.get<AiSessionList>('/api/ai/sessions', {
    params: { device_id: deviceId },
  });
  return data;
}

export async function getAiSession(sessionId: string): Promise<AiSessionDetail> {
  const { data } = await client.get<AiSessionDetail>(`/api/ai/sessions/${sessionId}`);
  return data;
}

export async function createAiSession(deviceId: string): Promise<AiSessionDetail> {
  const { data } = await client.post<AiSessionDetail>('/api/ai/sessions', null, {
    params: { device_id: deviceId },
  });
  return data;
}

export async function activateAiSession(sessionId: string, deviceId: string): Promise<AiSessionDetail> {
  const { data } = await client.post<AiSessionDetail>(`/api/ai/sessions/${sessionId}/activate`, null, {
    params: { device_id: deviceId },
  });
  return data;
}

export async function deleteAiSession(sessionId: string): Promise<void> {
  await client.delete(`/api/ai/sessions/${sessionId}`);
}

export async function uploadAiAttachment(file: File): Promise<AiAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post<AiAttachment>('/api/ai/attachments', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
}
