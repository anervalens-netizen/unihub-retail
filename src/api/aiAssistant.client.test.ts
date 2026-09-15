// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  consumeAiStream,
  createAiConversation,
  listAiConversations,
  listAiMessages,
  openAiTurnStream,
  steerAiTurn,
  stopAiTurn,
  type AiStreamEvent,
} from './aiAssistant';
import type { AiComposerSubmission } from '../features/ai-assistant/types';

const RAW_CONVERSATION = {
  id: 'c1',
  title: 'Analiză',
  effort: 'high',
  created_at: '2026-09-15T09:00:00Z',
  updated_at: '2026-09-15T09:30:00Z',
};

const RAW_MESSAGE = {
  id: 'm1',
  role: 'assistant',
  text: 'Gata',
  status: 'stopped',
  created_at: '2026-09-15T10:00:00Z',
  attachments: [
    {
      id: 'a1',
      filename: 'raport.xlsx',
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size_bytes: 2048,
      kind: 'output',
      download_url: '/api/ai/artifacts/a1/download',
    },
  ],
};

const fetchMock = vi.fn();

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function submission(overrides: Partial<AiComposerSubmission> = {}): AiComposerSubmission {
  return {
    text: 'raport pe august',
    effort: 'xhigh',
    includeCurrentView: true,
    currentView: { retail: null, locationHref: 'https://retail.unihub.ro/hub' },
    files: [],
    mode: 'send',
    ...overrides,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AI assistant REST transport', () => {
  it('maps the conversation list and creation payloads', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [RAW_CONVERSATION] }));
    const conversations = await listAiConversations();
    expect(conversations).toEqual([{
      id: 'c1',
      title: 'Analiză',
      effort: 'high',
      createdAt: '2026-09-15T09:00:00Z',
      updatedAt: '2026-09-15T09:30:00Z',
    }]);
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/ai/conversations');

    fetchMock.mockResolvedValueOnce(jsonResponse(RAW_CONVERSATION));
    await createAiConversation('max');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain('/api/ai/conversations');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ effort: 'max' });
  });

  it('maps persisted messages and downgrades a stopped run to an error bubble', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [RAW_MESSAGE] }));

    const messages = await listAiMessages('c1');

    expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/ai/conversations/c1/messages');
    expect(messages).toEqual([{
      id: 'm1',
      role: 'assistant',
      text: 'Gata',
      status: 'error',
      createdAt: '2026-09-15T10:00:00Z',
      attachments: [{
        id: 'a1',
        filename: 'raport.xlsx',
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        sizeBytes: 2048,
        kind: 'output',
        downloadUrl: '/api/ai/artifacts/a1/download',
      }],
    }]);
  });

  it('sends one multipart turn body with text, effort, current view and files', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));
    const file = new File(['store,value\nA,1\n'], 'raport.csv', { type: 'text/csv' });

    const response = await openAiTurnStream('c1', submission({ files: [file] }), new AbortController().signal);

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/ai/conversations/c1/turn');
    expect(init.method).toBe('POST');
    const form = init.body as FormData;
    expect(form.get('text')).toBe('raport pe august');
    expect(form.get('effort')).toBe('xhigh');
    expect(JSON.parse(String(form.get('current_view')))).toEqual(submission().currentView);
    expect((form.get('files') as File).name).toBe('raport.csv');
  });

  it('omits the current view when the owner disabled page context', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));

    await openAiTurnStream('c1', submission({ includeCurrentView: false, currentView: null }), new AbortController().signal);

    const form = (fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData;
    expect(form.get('current_view')).toBeNull();
    expect(form.get('files')).toBeNull();
  });

  it('maps an accepted steer response and posts stop without a body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ accepted: true, message: RAW_MESSAGE }));
    const message = await steerAiTurn('c1', submission({ mode: 'steer' }));
    expect(message.id).toBe('m1');
    expect(message.status).toBe('error');
    const steerCall = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(steerCall[0]).toContain('/api/ai/conversations/c1/steer');

    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    await stopAiTurn('c1');
    const stopCall = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(stopCall[0]).toContain('/api/ai/conversations/c1/stop');
    expect(stopCall[1].method).toBe('POST');
  });
});

describe('AI assistant stream decoding', () => {
  function streamResponse(chunks: string[], close = true): Response {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        if (close) controller.close();
      },
    });
    return new Response(body, { status: 200 });
  }

  it('decodes every event kind and drops unknown ones', async () => {
    const events: AiStreamEvent[] = [];
    await consumeAiStream(streamResponse([
      '{"type":"user_message","message":{"id":"u1","role":"user","text":"salut","status":"complete","created_at":"2026-09-15T10:00:00Z"}}\n',
      '{"type":"status","message":"Lucrez"}\n',
      '{"type":"delta","text":"parțial"}\n',
      '{"type":"stopped"}\n',
      '{"type":"error","message":"a picat"}\n',
      '{"type":"unknown_future_event"}\n',
      '{"type":"delta"}\n',
    ]), (event) => events.push(event));

    expect(events).toEqual([
      {
        type: 'user_message',
        message: {
          id: 'u1',
          role: 'user',
          text: 'salut',
          status: 'complete',
          createdAt: '2026-09-15T10:00:00Z',
          attachments: undefined,
        },
      },
      { type: 'status', message: 'Lucrez' },
      { type: 'delta', text: 'parțial' },
      { type: 'stopped' },
      { type: 'error', message: 'a picat' },
    ]);
  });

  it('keeps a complete event without a continuation id', async () => {
    const events: AiStreamEvent[] = [];
    await consumeAiStream(streamResponse([
      '{"type":"complete","message":{"id":"m9","role":"assistant","text":"gata","status":"complete","created_at":"2026-09-15T10:00:00Z"}}\n',
    ]), (event) => events.push(event));

    expect(events).toEqual([expect.objectContaining({
      type: 'complete',
      previousResponseId: null,
      message: expect.objectContaining({ id: 'm9' }),
    })]);
  });

  it('flushes a final JSON line that arrives without a trailing newline', async () => {
    const onEvent = vi.fn();
    await consumeAiStream(streamResponse([
      '{"type":"delta","text":"fără"}\n',
      '{"type":"delta","text":"newline"}',
    ]), onEvent);

    expect(onEvent).toHaveBeenNthCalledWith(1, { type: 'delta', text: 'fără' });
    expect(onEvent).toHaveBeenNthCalledWith(2, { type: 'delta', text: 'newline' });
  });

  it('refuses a stream response without a body', async () => {
    const response = new Response(null, { status: 204 });
    await expect(consumeAiStream(response, vi.fn())).rejects.toThrow('no body');
  });
});
