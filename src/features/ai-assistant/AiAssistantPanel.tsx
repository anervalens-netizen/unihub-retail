import {
  Bot, ChevronDown, FileText, Maximize2, MessageSquarePlus, Paperclip, PanelRightClose,
  Send, Sparkles, Square, X,
} from 'lucide-react';
import {
  useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

import type { RetailContextUrlState } from '../../lib/insightDeepLink';
import { usePersistentState } from '../../lib/usePersistentState';
import { cn } from '../../lib/utils';
import type {
  AiArtifactAttachment, AiChatMessage, AiComposerSubmission, AiReasoningEffort, AiRunStatus,
} from './types';

const MIN_DESKTOP_WIDTH = 380;
const MAX_DESKTOP_WIDTH = 680;
const DEFAULT_DESKTOP_WIDTH = 460;
const EFFORTS: Array<{ value: AiReasoningEffort; label: string }> = [
  { value: 'none', label: 'None' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'xhigh', label: 'XHigh' },
  { value: 'max', label: 'Max' },
];

interface AiAssistantPanelProps {
  canAccess: boolean;
  currentContext: RetailContextUrlState | null;
  messages: AiChatMessage[];
  runStatus: AiRunStatus;
  onSubmit: (submission: AiComposerSubmission) => void;
  onStop: () => void;
  onNewConversation?: () => void;
}

function contextLabel(context: RetailContextUrlState | null): string {
  if (!context) return 'Fără context disponibil';
  const filters = Object.values(context.filters ?? {}).flatMap((value) => Array.isArray(value) ? value : value ? [value] : []);
  return `${context.tab} · ${context.period}${filters.length ? ` · ${filters.length} filtre` : ''}`;
}

function formatFileSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentChip({ attachment, assistant }: { attachment: AiArtifactAttachment; assistant: boolean }) {
  const className = cn(
    'flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs',
    assistant ? 'bg-slate-50 dark:bg-slate-800' : 'bg-white/10',
    attachment.downloadUrl && 'hover:ring-1 hover:ring-indigo-300 dark:hover:ring-indigo-700',
  );
  const content = <>
    <FileText size={14} aria-hidden="true" />
    <span className="min-w-0 flex-1 truncate">{attachment.filename}</span>
    <span className="shrink-0 opacity-70">{formatFileSize(attachment.sizeBytes)}</span>
  </>;
  return attachment.downloadUrl
    ? <a href={attachment.downloadUrl} className={className} download={attachment.filename}>{content}</a>
    : <div className={className}>{content}</div>;
}

function MessageBubble({ message }: { message: AiChatMessage }) {
  const assistant = message.role === 'assistant';
  return <div className={cn('flex', assistant ? 'justify-start' : 'justify-end')}>
    <div className={cn(
      'max-w-[92%] rounded-2xl px-3.5 py-3 text-sm leading-6 shadow-sm',
      assistant
        ? 'border border-slate-200 bg-white text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200'
        : 'bg-indigo-600 text-white',
    )}>
      {assistant && <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-indigo-500"><Sparkles size={12} aria-hidden="true" />UniHub AI</div>}
      <div className="whitespace-pre-wrap">{message.text}</div>
      {message.attachments?.length ? <div className="mt-2 space-y-1.5">
        {message.attachments.map((attachment) => <AttachmentChip key={attachment.id} attachment={attachment} assistant={assistant} />)}
      </div> : null}
      {message.status === 'streaming' && <span className="ml-1 inline-block h-3 w-1 animate-pulse rounded-full bg-current align-middle" aria-label="Răspuns în curs" />}
      {message.status === 'error' && <div className="mt-2 text-xs font-semibold text-red-500">Răspuns întrerupt</div>}
    </div>
  </div>;
}

function AiEmptyState({ runtimeUnavailable }: { runtimeUnavailable: boolean }) {
  return <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
    <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300"><Bot size={28} aria-hidden="true" /></div>
    <h2 className="text-base font-bold text-slate-900 dark:text-white">UniHub AI</h2>
    <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500 dark:text-slate-400">
      Cere analize, rapoarte sau fișiere. Agentul poate folosi contextul paginii curente și sandboxul lui de lucru.
    </p>
    {runtimeUnavailable && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">Runtime-ul UniHub AI nu este disponibil momentan.</p>}
  </div>;
}

const composerPlaceholder = (steering: boolean, stopping: boolean): string => {
  if (steering) return 'Scrie pentru a ghida următorul pas…';
  if (stopping) return 'Rularea se oprește…';
  return 'Întreabă UniHub AI…';
};

function Composer({
  context, runStatus, onSubmit, onStop,
}: {
  context: RetailContextUrlState | null;
  runStatus: AiRunStatus;
  onSubmit: (submission: AiComposerSubmission) => void;
  onStop: () => void;
}) {
  const [draft, setDraft] = useState('');
  const [effort, setEffort] = usePersistentState<AiReasoningEffort>('unihub_ai_effort', 'high');
  const [includeContext, setIncludeContext] = usePersistentState('unihub_ai_include_context', true);
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const running = runStatus === 'running' || runStatus === 'stopping';
  const steering = runStatus === 'running';
  const stopping = runStatus === 'stopping';
  const unavailable = runStatus === 'unavailable';

  // A stop in flight is never steerable: the runtime rejects every control
  // request once stopping begins, so the draft is preserved, not queued.
  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text && files.length === 0) return;
    if (unavailable || stopping) return;
    onSubmit({
      text,
      effort,
      includeCurrentView: includeContext,
      currentView: includeContext ? {
        retail: context,
        locationHref: typeof window === 'undefined' ? '' : window.location.href,
      } : null,
      files,
      mode: steering ? 'steer' : 'send',
    });
    setDraft('');
    setFiles([]);
  }, [context, draft, effort, files, includeContext, onSubmit, steering, stopping, unavailable]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const next = Array.from(event.target.files ?? []);
    if (next.length) setFiles((current) => [...current, ...next]);
    event.target.value = '';
  }

  return <div className="border-t border-slate-200 bg-white/95 p-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
    {files.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">
      {files.map((file, index) => <span key={`${file.name}-${file.lastModified}-${index}`} className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"><Paperclip size={12} aria-hidden="true" /><span className="max-w-40 truncate">{file.name}</span><button type="button" aria-label={`Elimină ${file.name}`} onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={12} aria-hidden="true" /></button></span>)}
    </div>}
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-2 shadow-sm focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100 dark:border-slate-700 dark:bg-slate-900 dark:focus-within:border-indigo-700 dark:focus-within:ring-indigo-950">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={composerPlaceholder(steering, stopping)}
        rows={3}
        className="max-h-40 min-h-16 w-full resize-none bg-transparent px-1.5 py-1 text-sm text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100"
        aria-label="Mesaj pentru UniHub AI"
      />
      <div className="flex flex-wrap items-center gap-1.5 pt-1">
        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFiles} />
        <button type="button" onClick={() => fileInputRef.current?.click()} className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800" aria-label="Atașează fișiere"><Paperclip size={16} aria-hidden="true" /></button>
        <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800">
          <input type="checkbox" checked={includeContext} onChange={(event) => setIncludeContext(event.target.checked)} className="accent-indigo-600" />
          Context
        </label>
        <label className="relative inline-flex items-center">
          <span className="sr-only">Reasoning effort</span>
          <select value={effort} onChange={(event) => setEffort(event.target.value as AiReasoningEffort)} className="appearance-none rounded-lg bg-transparent py-1.5 pl-2 pr-7 text-xs font-semibold text-slate-600 hover:bg-slate-200 focus:outline-none dark:text-slate-300 dark:hover:bg-slate-800">
            {EFFORTS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <ChevronDown size={13} className="pointer-events-none absolute right-2 text-slate-400" aria-hidden="true" />
        </label>
        <div className="ml-auto flex items-center gap-1.5">
          {running && <button type="button" disabled={runStatus === 'stopping'} onClick={onStop} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"><Square size={12} fill="currentColor" aria-hidden="true" />Stop</button>}
          <button type="button" disabled={unavailable || stopping || (!draft.trim() && files.length === 0)} onClick={submit} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"><Send size={13} aria-hidden="true" />{running ? 'Steer' : 'Trimite'}</button>
        </div>
      </div>
    </div>
    <div className="mt-1.5 truncate px-1 text-[10px] text-slate-400">{includeContext ? `Context: ${contextLabel(context)}` : 'Contextul paginii este oprit'}</div>
  </div>;
}

export function AiAssistantPanel({
  canAccess, currentContext, messages, runStatus, onSubmit, onStop, onNewConversation,
}: AiAssistantPanelProps) {
  const [open, setOpen] = usePersistentState('unihub_ai_open', false);
  const [width, setWidth] = usePersistentState('unihub_ai_width', DEFAULT_DESKTOP_WIDTH);
  const resizingRef = useRef(false);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!canAccess) setOpen(false);
  }, [canAccess, setOpen]);

  useEffect(() => {
    function handleMove(event: PointerEvent) {
      if (!resizingRef.current) return;
      const next = Math.min(MAX_DESKTOP_WIDTH, Math.max(MIN_DESKTOP_WIDTH, window.innerWidth - event.clientX));
      setWidth(next);
    }
    function stopResize() { resizingRef.current = false; }
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', stopResize);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', stopResize);
    };
  }, [setWidth]);

  const latestMessageId = messages.at(-1)?.id;
  useEffect(() => {
    if (!latestMessageId || !open) return;
    const node = panelRef.current?.querySelector<HTMLElement>('[data-ai-message-list]');
    if (node && typeof node.scrollTo === 'function') {
      node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' });
    }
  }, [latestMessageId, open]);

  const messageList = useMemo(() => messages.filter((message) => message.role !== 'system'), [messages]);
  if (!canAccess) return null;

  function startResize(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    resizingRef.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  return <>
    {!open && <button type="button" onClick={() => setOpen(true)} className="fixed bottom-36 right-4 z-40 inline-flex size-11 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20 transition hover:-translate-y-0.5 hover:bg-indigo-700 lg:bottom-6" aria-label="Deschide UniHub AI"><Bot size={20} aria-hidden="true" /></button>}
    {open && <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/20 backdrop-blur-[1px] lg:static lg:z-auto lg:bg-transparent lg:backdrop-blur-none">
      <button type="button" aria-label="Închide UniHub AI" className="absolute inset-0 lg:hidden" onClick={() => setOpen(false)} />
      <aside
        ref={panelRef}
        aria-label="UniHub AI"
        style={{ '--ai-panel-width': `${width}px` } as React.CSSProperties}
        className="relative z-10 flex h-dvh w-full flex-col border-l border-slate-200 bg-slate-50 shadow-2xl dark:border-slate-800 dark:bg-slate-950 sm:max-w-[min(88vw,560px)] lg:w-[var(--ai-panel-width)] lg:max-w-none lg:shrink-0 lg:shadow-none"
      >
        <button type="button" tabIndex={-1} aria-label="Redimensionează panoul AI" onPointerDown={startResize} className="absolute inset-y-0 -left-1 hidden w-2 cursor-col-resize touch-none lg:block" />
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200 px-3 dark:border-slate-800">
          <div className="flex size-8 items-center justify-center rounded-xl bg-indigo-600 text-white"><Bot size={17} aria-hidden="true" /></div>
          <div className="min-w-0 flex-1"><div className="truncate text-sm font-bold text-slate-900 dark:text-white">UniHub AI</div><div className="truncate text-[10px] font-medium uppercase tracking-wide text-slate-400">Luna · Sandbox</div></div>
          {onNewConversation && <button type="button" onClick={onNewConversation} className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800" aria-label="Conversație nouă"><MessageSquarePlus size={16} aria-hidden="true" /></button>}
          <button type="button" onClick={() => setWidth(DEFAULT_DESKTOP_WIDTH)} className="hidden size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 lg:inline-flex" aria-label="Resetează lățimea panoului"><Maximize2 size={15} aria-hidden="true" /></button>
          <button type="button" onClick={() => setOpen(false)} className="inline-flex size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800" aria-label="Închide UniHub AI"><PanelRightClose size={17} aria-hidden="true" /></button>
        </header>
        <div data-ai-message-list className="min-h-0 flex-1 overflow-y-auto p-3">
          {messageList.length === 0 ? <AiEmptyState runtimeUnavailable={runStatus === 'unavailable'} /> : <div className="space-y-3">{messageList.map((message) => <MessageBubble key={message.id} message={message} />)}</div>}
        </div>
        <Composer context={currentContext} runStatus={runStatus} onSubmit={onSubmit} onStop={onStop} />
      </aside>
    </div>}
  </>;
}
