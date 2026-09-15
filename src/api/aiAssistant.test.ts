// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';

import { consumeAiStream } from './aiAssistant';

function streamResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(line));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

describe('AI assistant stream transport', () => {
  it('parses NDJSON deltas and a completed persisted message', async () => {
    const onEvent = vi.fn();
    await consumeAiStream(streamResponse([
      '{"type":"delta","text":"Ana"}\n',
      '{"type":"delta","text":"liză"}\n',
      '{"type":"complete","message":{"id":"m1","role":"assistant","text":"Analiză","status":"complete","created_at":"2026-09-15T10:00:00Z","attachments":[]}}\n',
    ]), onEvent);

    expect(onEvent).toHaveBeenNthCalledWith(1, { type: 'delta', text: 'Ana' });
    expect(onEvent).toHaveBeenNthCalledWith(2, { type: 'delta', text: 'liză' });
    expect(onEvent).toHaveBeenNthCalledWith(3, expect.objectContaining({
      type: 'complete',
      message: expect.objectContaining({ id: 'm1', text: 'Analiză' }),
    }));
  });

  it('ignores one malformed line and continues the stream', async () => {
    const onEvent = vi.fn();
    await consumeAiStream(streamResponse([
      'not-json\n',
      '{"type":"status","message":"Lucrez"}\n',
    ]), onEvent);
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith({ type: 'status', message: 'Lucrez' });
  });
});
