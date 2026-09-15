// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  AiChatMessage,
  AiComposerSubmission,
  AiConversation,
} from './types';
import { useAiAssistant } from './useAiAssistant';

const api = vi.hoisted(() => ({
  listAiConversations: vi.fn(),
  createAiConversation: vi.fn(),
  listAiMessages: vi.fn(),
  openAiTurnStream: vi.fn(),
  steerAiTurn: vi.fn(),
  stopAiTurn: vi.fn(),
  consumeAiStream: vi.fn(),
}));

vi.mock('../../api/aiAssistant', () => api);

const CONVERSATION: AiConversation = {
  id: 'c1',
  title: 'Conversație',
  effort: 'high',
  createdAt: '2026-09-15T09:00:00Z',
  updatedAt: '2026-09-15T09:00:00Z',
};

function message(id: string, role: 'user' | 'assistant', text: string): AiChatMessage {
  return { id, role, text, status: 'complete', createdAt: '2026-09-15T10:00:00Z' };
}

function submission(overrides: Partial<AiComposerSubmission> = {}): AiComposerSubmission {
  return {
    text: '',
    effort: 'high',
    includeCurrentView: false,
    currentView: null,
    files: [],
    mode: 'send',
    ...overrides,
  };
}

/** Boots one conversation and leaves the hook idle, ready to submit. */
async function bootIdleConversation(initialMessages: AiChatMessage[] = []) {
  api.listAiConversations.mockResolvedValue([CONVERSATION]);
  api.listAiMessages.mockResolvedValue(initialMessages);
  const view = renderHook(() => useAiAssistant(true));
  // Bootstrap must have selected the conversation before submit() can do anything.
  await waitFor(() => expect(api.listAiMessages).toHaveBeenCalledWith('c1'));
  await waitFor(() => expect(view.result.current.runStatus).toBe('idle'));
  return view;
}

/** Starts a turn whose transport never finishes until the returned release runs. */
async function bootRunningTurn() {
  let releaseStream: (() => void) | null = null;
  api.consumeAiStream.mockImplementation(
    () => new Promise<void>((resolve) => { releaseStream = resolve; }),
  );
  api.openAiTurnStream.mockResolvedValue(new Response(null, { status: 200 }));
  const view = await bootIdleConversation();
  await act(async () => {
    void view.result.current.submit(submission({ text: 'Analizează luna' }));
  });
  expect(view.result.current.runStatus).toBe('running');
  return {
    view,
    releaseStream: () => {
      releaseStream?.();
    },
  };
}

beforeEach(() => {
  sessionStorage.clear();
  for (const stub of Object.values(api)) stub.mockReset();
});

describe('useAiAssistant submission modes', () => {
  it('submits a file-only Turn with no text', async () => {
    const { result } = await bootIdleConversation();
    const file = new File(['store,value\nA,10\n'], 'only.csv', { type: 'text/csv' });

    await act(async () => {
      await result.current.submit(submission({ files: [file] }));
    });

    expect(api.openAiTurnStream).toHaveBeenCalledTimes(1);
    const [conversationId, sent] = api.openAiTurnStream.mock.calls[0] as [
      string,
      { text: string; files: File[] },
    ];
    expect(conversationId).toBe('c1');
    expect(sent.text).toBe('');
    expect(sent.files).toEqual([file]);
  });

  it('submits a file-only Steer while a run is active', async () => {
    const { view } = await bootRunningTurn();
    const file = new File(['store,value\nA,10\n'], 'only.csv', { type: 'text/csv' });
    api.steerAiTurn.mockResolvedValue(message('u2', 'user', ''));

    await act(async () => {
      await view.result.current.submit(submission({ files: [file], mode: 'steer' }));
    });

    expect(api.steerAiTurn).toHaveBeenCalledTimes(1);
    const [conversationId, sent] = api.steerAiTurn.mock.calls[0] as [
      string,
      { text: string; files: File[] },
    ];
    expect(conversationId).toBe('c1');
    expect(sent.text).toBe('');
    expect(sent.files).toEqual([file]);
  });
});

describe('useAiAssistant conversation selection epoch', () => {
  it('does not let a delayed bootstrap overwrite a newer New Conversation', async () => {
    // The bootstrap has already chosen conversation c1 and is awaiting its
    // message list when the owner starts a new conversation.
    let resolveBootstrapMessages: (value: AiChatMessage[]) => void = () => {};
    api.listAiConversations.mockResolvedValue([CONVERSATION]);
    api.listAiMessages.mockImplementation(
      () => new Promise<AiChatMessage[]>((resolve) => { resolveBootstrapMessages = resolve; }),
    );
    api.createAiConversation.mockResolvedValue({ ...CONVERSATION, id: 'c-new' });

    const { result } = renderHook(() => useAiAssistant(true));
    await waitFor(() => expect(api.listAiMessages).toHaveBeenCalledWith('c1'));

    await act(async () => {
      await result.current.newConversation();
    });
    expect(sessionStorage.getItem('unihub_ai_conversation')).toBe('c-new');
    expect(result.current.messages).toEqual([]);

    // The stale message list for c1 now lands. It must not become current.
    await act(async () => {
      resolveBootstrapMessages([message('u1', 'user', 'din conversația veche')]);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(sessionStorage.getItem('unihub_ai_conversation')).toBe('c-new');
    expect(result.current.messages).toEqual([]);
  });
});

describe('useAiAssistant steer ordering', () => {
  it('renders persisted messages in durable order even when Steer responses land out of order', async () => {
    const u1 = message('u1', 'user', 'start');
    const u2 = message('u2', 'user', 'prima');
    const u3 = message('u3', 'user', 'a doua');
    let serverMessages: AiChatMessage[] = [u1];

    const { view } = await bootRunningTurn();
    api.listAiMessages.mockImplementation(async () => serverMessages);

    let resolveFirstSteer: ((value: AiChatMessage) => void) | null = null;
    api.steerAiTurn
      // First request is accepted durably (ordinal 2) but its HTTP response is slow.
      .mockImplementationOnce(
        () => new Promise<AiChatMessage>((resolve) => { resolveFirstSteer = resolve; }),
      )
      // Second request is accepted durably afterwards (ordinal 3) and answers first.
      .mockImplementationOnce(async () => {
        serverMessages = [u1, u2, u3];
        return u3;
      });

    await act(async () => {
      void view.result.current.submit(submission({ text: 'prima', mode: 'steer' }));
      const second = view.result.current.submit(submission({ text: 'a doua', mode: 'steer' }));
      await second;
      await Promise.resolve();
    });

    const idsAfterFastResponse = view.result.current.messages.map((item) => item.id);
    expect(idsAfterFastResponse).toEqual(['u1', 'u2', 'u3']);

    await act(async () => {
      resolveFirstSteer?.(u2);
      await Promise.resolve();
      await Promise.resolve();
    });

    const finalIds = view.result.current.messages.map((item) => item.id);
    expect(finalIds).toEqual(['u1', 'u2', 'u3']);
    // HTTP response order was u3 then u2; the UI must never reflect that.
    expect(finalIds).not.toEqual(['u1', 'u3', 'u2']);
  });
});

describe('useAiAssistant stream durability', () => {
  it('keeps an active stream alive across a transient rerender', async () => {
    const { view, releaseStream } = await bootRunningTurn();
    const signal = api.openAiTurnStream.mock.calls[0]?.[2] as AbortSignal;

    view.rerender();

    expect(signal.aborted).toBe(false);
    expect(view.result.current.runStatus).toBe('running');

    await act(async () => {
      releaseStream();
    });
    await waitFor(() => expect(view.result.current.runStatus).toBe('idle'));
  });
});

describe('useAiAssistant stop and steer controls', () => {
  it('moves to stopping on Stop and back to running when the stop request fails', async () => {
    const { view } = await bootRunningTurn();
    api.stopAiTurn.mockRejectedValueOnce(new Error('offline'));

    await act(async () => {
      await view.result.current.stop();
    });

    expect(api.stopAiTurn).toHaveBeenCalledWith('c1');
    expect(view.result.current.runStatus).toBe('running');
  });

  it('keeps the run active while stopping is in flight', async () => {
    const { view } = await bootRunningTurn();
    let resolveStop: (() => void) | null = null;
    api.stopAiTurn.mockImplementation(
      () => new Promise<void>((resolve) => { resolveStop = resolve; }),
    );

    let pending: Promise<void> = Promise.resolve();
    await act(async () => {
      pending = view.result.current.stop();
      await Promise.resolve();
    });
    expect(view.result.current.runStatus).toBe('stopping');

    await act(async () => {
      resolveStop?.();
      await pending;
    });
    expect(view.result.current.runStatus).toBe('stopping');
    expect(api.steerAiTurn).not.toHaveBeenCalled();
  });
});
