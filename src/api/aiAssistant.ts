import { client, postStreaming } from './client';
import type {
  AiArtifactAttachment,
  AiChatMessage,
  AiComposerSubmission,
  AiConversation,
  AiReasoningEffort,
} from '../features/ai-assistant/types';

type RawArtifact = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  kind: 'input' | 'output';
  download_url: string;
  created_at: string;
};

type RawMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  status: 'complete' | 'streaming' | 'error' | 'stopped';
  created_at: string;
  attachments?: RawArtifact[];
};

type RawConversation = {
  id: string;
  title: string;
  effort: AiReasoningEffort;
  created_at: string;
  updated_at: string;
};

type RawConversationList = { items: RawConversation[] };
type RawMessageList = { items: RawMessage[] };
type RawSteerResponse = { accepted: boolean; message: RawMessage };

export type AiStreamEvent =
  | { type: 'user_message'; message: AiChatMessage }
  | { type: 'delta'; text: string }
  | { type: 'status'; message: string }
  | { type: 'complete'; message: AiChatMessage; previousResponseId?: string | null }
  | { type: 'stopped' }
  | { type: 'error'; message: string };

function mapArtifact(raw: RawArtifact): AiArtifactAttachment {
  return {
    id: raw.id,
    filename: raw.filename,
    mimeType: raw.mime_type,
    sizeBytes: raw.size_bytes,
    kind: raw.kind,
    downloadUrl: raw.download_url,
  };
}

function mapMessage(raw: RawMessage): AiChatMessage {
  return {
    id: raw.id,
    role: raw.role,
    text: raw.text,
    status: raw.status === 'stopped' ? 'error' : raw.status,
    createdAt: raw.created_at,
    attachments: raw.attachments?.map(mapArtifact),
  };
}

function mapConversation(raw: RawConversation): AiConversation {
  return {
    id: raw.id,
    title: raw.title,
    effort: raw.effort,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function submissionForm(submission: AiComposerSubmission): FormData {
  const data = new FormData();
  data.append('text', submission.text);
  data.append('effort', submission.effort);
  if (submission.currentView) {
    data.append('current_view', JSON.stringify(submission.currentView));
  }
  for (const file of submission.files) data.append('files', file, file.name);
  return data;
}

export async function listAiConversations(): Promise<AiConversation[]> {
  const { data } = await client.get<RawConversationList>('/api/ai/conversations');
  return data.items.map(mapConversation);
}

export async function createAiConversation(
  effort: AiReasoningEffort = 'high',
): Promise<AiConversation> {
  const { data } = await client.post<RawConversation>('/api/ai/conversations', { effort });
  return mapConversation(data);
}

export async function listAiMessages(conversationId: string): Promise<AiChatMessage[]> {
  const { data } = await client.get<RawMessageList>(`/api/ai/conversations/${conversationId}/messages`);
  return data.items.map(mapMessage);
}

export async function openAiTurnStream(
  conversationId: string,
  submission: AiComposerSubmission,
  signal: AbortSignal,
): Promise<Response> {
  return postStreaming(
    `/api/ai/conversations/${conversationId}/turn`,
    submissionForm(submission),
    { signal },
  );
}

export async function steerAiTurn(
  conversationId: string,
  submission: AiComposerSubmission,
): Promise<AiChatMessage> {
  const { data } = await client.post<RawSteerResponse>(
    `/api/ai/conversations/${conversationId}/steer`,
    submissionForm(submission),
    { timeoutMs: 30_000 },
  );
  return mapMessage(data.message);
}

export async function stopAiTurn(conversationId: string): Promise<void> {
  await client.post(`/api/ai/conversations/${conversationId}/stop`, undefined, {
    timeoutMs: 15_000,
  });
}

function parseStreamEvent(raw: unknown): AiStreamEvent | null {
  if (!raw || typeof raw !== 'object' || !('type' in raw)) return null;
  const event = raw as Record<string, unknown>;
  switch (event.type) {
    case 'user_message':
      return event.message && typeof event.message === 'object'
        ? { type: 'user_message', message: mapMessage(event.message as RawMessage) }
        : null;
    case 'delta':
      return typeof event.text === 'string' ? { type: 'delta', text: event.text } : null;
    case 'status':
      return typeof event.message === 'string' ? { type: 'status', message: event.message } : null;
    case 'complete':
      return event.message && typeof event.message === 'object'
        ? {
          type: 'complete',
          message: mapMessage(event.message as RawMessage),
          previousResponseId: typeof event.previous_response_id === 'string'
            ? event.previous_response_id
            : null,
        }
        : null;
    case 'stopped':
      return { type: 'stopped' };
    case 'error':
      return typeof event.message === 'string' ? { type: 'error', message: event.message } : null;
    default:
      return null;
  }
}

export async function consumeAiStream(
  response: Response,
  onEvent: (event: AiStreamEvent) => void,
): Promise<void> {
  if (!response.body) throw new Error('AI stream response has no body');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let newline = buffer.indexOf('\n');
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) {
        try {
          const parsed = parseStreamEvent(JSON.parse(line));
          if (parsed) onEvent(parsed);
        } catch {
          // Ignore one malformed transport line without discarding the run.
        }
      }
      newline = buffer.indexOf('\n');
    }
    if (done) break;
  }
  const tail = buffer.trim();
  if (tail) {
    const parsed = parseStreamEvent(JSON.parse(tail));
    if (parsed) onEvent(parsed);
  }
}
