import { useCallback, useEffect, useRef, useState } from 'react';

import {
  consumeAiStream,
  createAiConversation,
  listAiConversations,
  listAiMessages,
  openAiTurnStream,
  steerAiTurn,
  stopAiTurn,
  type AiStreamEvent,
} from '../../api/aiAssistant';
import { usePersistentState } from '../../lib/usePersistentState';
import type {
  AiChatMessage,
  AiComposerSubmission,
  AiRunStatus,
} from './types';

const STREAMING_MESSAGE_ID = 'unihub-ai-streaming';

function streamingMessage(): AiChatMessage {
  return {
    id: STREAMING_MESSAGE_ID,
    role: 'assistant',
    text: '',
    status: 'streaming',
    createdAt: new Date().toISOString(),
  };
}

function replaceStreaming(
  messages: AiChatMessage[],
  replacement: AiChatMessage,
): AiChatMessage[] {
  const withoutPlaceholder = messages.filter((item) => item.id !== STREAMING_MESSAGE_ID);
  return [...withoutPlaceholder, replacement];
}

export function useAiAssistant(enabled: boolean) {
  const [conversationId, setConversationId] = usePersistentState<string | null>(
    'unihub_ai_conversation',
    null,
  );
  const [messages, setMessages] = useState<AiChatMessage[]>([]);
  const [runStatus, setRunStatus] = useState<AiRunStatus>(enabled ? 'idle' : 'unavailable');
  const initializedRef = useRef(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  const loadConversation = useCallback(async (id: string) => {
    const next = await listAiMessages(id);
    setConversationId(id);
    setMessages(next);
  }, [setConversationId]);

  useEffect(() => {
    if (!enabled) {
      initializedRef.current = false;
      setRunStatus('unavailable');
      setMessages([]);
      return;
    }
    if (initializedRef.current) return;
    initializedRef.current = true;
    let cancelled = false;
    void (async () => {
      try {
        const conversations = await listAiConversations();
        if (cancelled) return;
        const preferred = conversationId
          ? conversations.find((item) => item.id === conversationId)
          : undefined;
        const active = preferred ?? conversations[0] ?? await createAiConversation('high');
        if (cancelled) return;
        await loadConversation(active.id);
        if (!cancelled) setRunStatus('idle');
      } catch (error) {
        if (!cancelled) {
          console.error('UniHub AI bootstrap failed', error);
          setRunStatus('unavailable');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, enabled, loadConversation]);

  useEffect(() => () => {
    streamAbortRef.current?.abort();
  }, []);

  const handleStreamEvent = useCallback((event: AiStreamEvent) => {
    if (event.type === 'user_message') {
      setMessages((current) => [...current, event.message, streamingMessage()]);
      return;
    }
    if (event.type === 'delta') {
      setMessages((current) => current.map((message) => (
        message.id === STREAMING_MESSAGE_ID
          ? { ...message, text: `${message.text}${event.text}` }
          : message
      )));
      return;
    }
    if (event.type === 'complete') {
      setMessages((current) => replaceStreaming(current, event.message));
      setRunStatus('idle');
      return;
    }
    if (event.type === 'stopped') {
      setMessages((current) => replaceStreaming(current, {
        id: `${STREAMING_MESSAGE_ID}-stopped-${Date.now()}`,
        role: 'assistant',
        text: 'Rularea a fost oprită.',
        status: 'error',
        createdAt: new Date().toISOString(),
      }));
      setRunStatus('idle');
      return;
    }
    if (event.type === 'error') {
      setMessages((current) => replaceStreaming(current, {
        id: `${STREAMING_MESSAGE_ID}-error-${Date.now()}`,
        role: 'assistant',
        text: event.message,
        status: 'error',
        createdAt: new Date().toISOString(),
      }));
      setRunStatus('idle');
    }
  }, []);

  const submit = useCallback(async (submission: AiComposerSubmission) => {
    if (!enabled || !conversationId) return;
    if (submission.mode === 'steer' && (runStatus === 'running' || runStatus === 'stopping')) {
      try {
        const userMessage = await steerAiTurn(conversationId, submission);
        setMessages((current) => [...current, userMessage]);
        if (runStatus === 'stopping') setRunStatus('running');
      } catch (error) {
        console.error('UniHub AI steer failed', error);
      }
      return;
    }
    if (runStatus !== 'idle') return;

    const controller = new AbortController();
    streamAbortRef.current = controller;
    setRunStatus('running');
    try {
      const response = await openAiTurnStream(conversationId, submission, controller.signal);
      await consumeAiStream(response, handleStreamEvent);
      setRunStatus((current) => current === 'unavailable' ? current : 'idle');
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error('UniHub AI run failed', error);
      handleStreamEvent({ type: 'error', message: 'UniHub AI nu a putut finaliza cererea.' });
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
    }
  }, [conversationId, enabled, handleStreamEvent, runStatus]);

  const stop = useCallback(async () => {
    if (!conversationId || runStatus !== 'running') return;
    setRunStatus('stopping');
    try {
      await stopAiTurn(conversationId);
    } catch (error) {
      console.error('UniHub AI stop failed', error);
      setRunStatus('running');
    }
  }, [conversationId, runStatus]);

  const newConversation = useCallback(async () => {
    if (!enabled || runStatus === 'running' || runStatus === 'stopping') return;
    try {
      const created = await createAiConversation('high');
      setConversationId(created.id);
      setMessages([]);
      setRunStatus('idle');
    } catch (error) {
      console.error('UniHub AI conversation creation failed', error);
      setRunStatus('unavailable');
    }
  }, [enabled, runStatus, setConversationId]);

  return {
    messages,
    runStatus,
    submit,
    stop,
    newConversation,
  };
}
