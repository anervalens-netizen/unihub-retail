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

function terminalMessage(kind: 'stopped' | 'error', text: string): AiChatMessage {
  return {
    id: `${STREAMING_MESSAGE_ID}-${kind}-${Date.now()}`,
    role: 'assistant',
    text,
    status: 'error',
    createdAt: new Date().toISOString(),
  };
}

function replaceStreaming(
  messages: AiChatMessage[],
  replacement: AiChatMessage,
): AiChatMessage[] {
  return [...messages.filter((item) => item.id !== STREAMING_MESSAGE_ID), replacement];
}

function mergePersistedWithStreaming(
  persisted: AiChatMessage[],
  current: AiChatMessage[],
): AiChatMessage[] {
  const streaming = current.find((item) => item.id === STREAMING_MESSAGE_ID);
  return streaming ? [...persisted, streaming] : persisted;
}

function useStreamEvents(
  setMessages: React.Dispatch<React.SetStateAction<AiChatMessage[]>>,
  setRunStatus: React.Dispatch<React.SetStateAction<AiRunStatus>>,
) {
  return useCallback((event: AiStreamEvent) => {
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
      setMessages((current) => replaceStreaming(
        current,
        terminalMessage('stopped', 'Rularea a fost oprită.'),
      ));
      setRunStatus('idle');
      return;
    }
    if (event.type === 'error') {
      setMessages((current) => replaceStreaming(
        current,
        terminalMessage('error', event.message),
      ));
      setRunStatus('idle');
    }
  }, [setMessages, setRunStatus]);
}

export function useAiAssistant(enabled: boolean) {
  const [conversationId, setConversationId] = usePersistentState<string | null>(
    'unihub_ai_conversation',
    null,
  );
  const [messages, setMessages] = useState<AiChatMessage[]>([]);
  const [runStatus, setRunStatus] = useState<AiRunStatus>(enabled ? 'idle' : 'unavailable');
  const initializedRef = useRef(false);
  const selectionEpochRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const handleStreamEvent = useStreamEvents(setMessages, setRunStatus);

  const loadConversation = useCallback(async (id: string, epoch: number) => {
    const next = await listAiMessages(id);
    if (selectionEpochRef.current !== epoch) return false;
    setConversationId(id);
    setMessages(next);
    return true;
  }, [setConversationId]);

  useEffect(() => {
    if (!enabled) {
      if (!initializedRef.current) setRunStatus('unavailable');
      return;
    }
    if (initializedRef.current) return;
    initializedRef.current = true;
    const epoch = selectionEpochRef.current + 1;
    selectionEpochRef.current = epoch;
    let cancelled = false;
    void (async () => {
      try {
        const conversations = await listAiConversations();
        if (cancelled || selectionEpochRef.current !== epoch) return;
        const preferred = conversationId
          ? conversations.find((item) => item.id === conversationId)
          : undefined;
        const active = preferred ?? conversations[0] ?? await createAiConversation('high');
        if (cancelled || selectionEpochRef.current !== epoch) return;
        if (await loadConversation(active.id, epoch) && !cancelled) setRunStatus('idle');
      } catch (error) {
        if (!cancelled && selectionEpochRef.current === epoch) {
          console.error('UniHub AI bootstrap failed', error);
          initializedRef.current = false;
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

  const refreshPersisted = useCallback(async (id: string) => {
    const persisted = await listAiMessages(id);
    setMessages((current) => mergePersistedWithStreaming(persisted, current));
  }, []);

  const submitSteer = useCallback(async (
    id: string,
    submission: AiComposerSubmission,
  ) => {
    try {
      await steerAiTurn(id, submission);
      await refreshPersisted(id);
      setRunStatus((current) => current === 'stopping' ? 'running' : current);
    } catch (error) {
      console.error('UniHub AI steer failed', error);
      try { await refreshPersisted(id); } catch { /* transport error remains visible in console */ }
    }
  }, [refreshPersisted]);

  const submitTurn = useCallback(async (
    id: string,
    submission: AiComposerSubmission,
  ) => {
    const controller = new AbortController();
    streamAbortRef.current = controller;
    setRunStatus('running');
    try {
      const response = await openAiTurnStream(id, submission, controller.signal);
      await consumeAiStream(response, handleStreamEvent);
      setRunStatus((current) => current === 'unavailable' ? current : 'idle');
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error('UniHub AI run failed', error);
      handleStreamEvent({ type: 'error', message: 'UniHub AI nu a putut finaliza cererea.' });
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
    }
  }, [handleStreamEvent]);

  const submit = useCallback(async (submission: AiComposerSubmission) => {
    if (!enabled || !conversationId) return;
    if (submission.mode === 'steer' && (runStatus === 'running' || runStatus === 'stopping')) {
      await submitSteer(conversationId, submission);
      return;
    }
    if (runStatus !== 'idle') return;
    await submitTurn(conversationId, submission);
  }, [conversationId, enabled, runStatus, submitSteer, submitTurn]);

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
    const epoch = selectionEpochRef.current + 1;
    selectionEpochRef.current = epoch;
    try {
      const created = await createAiConversation('high');
      if (selectionEpochRef.current !== epoch) return;
      setConversationId(created.id);
      setMessages([]);
      setRunStatus('idle');
      initializedRef.current = true;
    } catch (error) {
      if (selectionEpochRef.current !== epoch) return;
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
