import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  Database,
  FileText,
  Menu,
  Paperclip,
  PlusSquare,
  Send,
  User,
  WifiOff,
  X,
} from 'lucide-react';
import { AiWebSocket, type AiEvent } from '../api/ai';
import {
  activateAiSession,
  createAiSession,
  getAiDeviceId,
  listAiSessions,
  uploadAiAttachment,
  type AiAttachment,
  type AiSessionMessage,
  type AiSessionSummary,
} from '../api/aiSessions';
import { cn } from '../lib/utils';

interface ChartSpec {
  chartType: 'bar' | 'line' | 'pie' | 'area';
  title?: string;
  data: Record<string, unknown>[];
  keys: string[];
  xKey?: string;
  colors?: string[];
}

type MessageBlock =
  | { kind: 'text'; content: string }
  | { kind: 'chart'; spec: ChartSpec };

interface Message {
  id: string;
  role: 'user' | 'assistant';
  blocks: MessageBlock[];
  timestamp: Date;
  toolsUsed?: string[];
  attachments?: AiAttachment[];
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'offline';

const CHART_COLORS = ['#0f766e', '#f59e0b', '#2563eb', '#ef4444', '#16a34a', '#8b5cf6'];

function formatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

function formatSessionTime(value: string): string {
  const date = new Date(value);
  return date.toLocaleString('ro-RO', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseBlocks(text: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  const chartRegex = /```chart\n([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = chartRegex.exec(text)) !== null) {
    if (match.index > last) {
      const chunk = text.slice(last, match.index).trim();
      if (chunk) blocks.push({ kind: 'text', content: chunk });
    }
    try {
      blocks.push({ kind: 'chart', spec: JSON.parse(match[1]) as ChartSpec });
    } catch {
      blocks.push({ kind: 'text', content: match[0] });
    }
    last = match.index + match[0].length;
  }

  const remaining = text.slice(last).trim();
  if (remaining) blocks.push({ kind: 'text', content: remaining });
  return blocks.length > 0 ? blocks : [{ kind: 'text', content: text }];
}

function normalizeMessages(items: AiSessionMessage[]): Message[] {
  return items.map((item) => ({
    id: item.id,
    role: item.role,
    blocks: parseBlocks(item.content),
    timestamp: new Date(item.timestamp),
  }));
}

function attachmentLabel(file: AiAttachment): string {
  const kb = Math.max(1, Math.round(file.size / 1024));
  return `${file.name} · ${kb} KB`;
}

function ChartBlock({ spec }: { spec: ChartSpec }) {
  const xKey = spec.xKey ?? 'name';
  const colors = spec.colors ?? CHART_COLORS;
  const keys = spec.keys ?? ['value'];
  const common = {
    data: spec.data as Record<string, number | string>[],
    margin: { top: 4, right: 8, bottom: 4, left: 0 },
  };

  let chart: React.ReactNode = null;
  if (spec.chartType === 'pie') {
    chart = (
      <PieChart>
        <Pie data={spec.data} dataKey={keys[0] ?? 'value'} nameKey={xKey} cx="50%" cy="50%" outerRadius={80} label>
          {spec.data.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    );
  } else if (spec.chartType === 'line') {
    chart = (
      <LineChart {...common}>
        <CartesianGrid strokeDasharray="3 3" stroke="#dbe4ea" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((key, i) => (
          <Line key={key} type="monotone" dataKey={key} stroke={colors[i % colors.length]} dot={false} strokeWidth={2} />
        ))}
      </LineChart>
    );
  } else if (spec.chartType === 'area') {
    chart = (
      <AreaChart {...common}>
        <CartesianGrid strokeDasharray="3 3" stroke="#dbe4ea" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((key, i) => (
          <Area key={key} type="monotone" dataKey={key} stroke={colors[i % colors.length]} fill={`${colors[i % colors.length]}33`} strokeWidth={2} />
        ))}
      </AreaChart>
    );
  } else {
    chart = (
      <BarChart {...common}>
        <CartesianGrid strokeDasharray="3 3" stroke="#dbe4ea" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((key, i) => (
          <Bar key={key} dataKey={key} fill={colors[i % colors.length]} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-emerald-100 bg-emerald-50/80 p-3 dark:border-slate-700 dark:bg-slate-900/50">
      {spec.title && <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{spec.title}</p>}
      <ResponsiveContainer width="100%" height={220} minWidth={0}>{chart as React.ReactElement}</ResponsiveContainer>
    </div>
  );
}

export default function AIChat() {
  const deviceId = useMemo(() => getAiDeviceId(), []);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [toolInProgress, setToolInProgress] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AiSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const [attachments, setAttachments] = useState<AiAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<AiWebSocket | null>(null);

  const streamBufRef = useRef('');
  const streamIdRef = useRef('');
  const streamToolsRef = useRef<string[]>([]);

  const refreshSessions = useCallback(async (expectedActiveId?: string | null) => {
    const list = await listAiSessions(deviceId);
    setSessions(list.sessions);
    const nextActiveId = expectedActiveId ?? list.active_session_id;
    setActiveSessionId(nextActiveId);
    return nextActiveId;
  }, [deviceId]);

  const reconnectSocket = useCallback((sessionId: string | null) => {
    const token = localStorage.getItem('unihub_token') ?? '';
    if (!token || !sessionId) return;
    wsRef.current?.disconnect();
    const ws = new AiWebSocket(token, deviceId, sessionId, handleEvent, handleClose);
    wsRef.current = ws;
    setStatus('connecting');
    ws.connect();
  }, [deviceId]);

  const loadInitialState = useCallback(async () => {
    setLoadingSession(true);
    const activeId = await refreshSessions();
    if (activeId) {
      const detail = await activateAiSession(activeId, deviceId);
      setMessages(normalizeMessages(detail.messages));
      reconnectSocket(activeId);
    }
    setLoadingSession(false);
  }, [deviceId, reconnectSocket, refreshSessions]);

  const handleClose = useCallback(() => {
    setStatus((current) => (current === 'offline' ? 'offline' : 'disconnected'));
  }, []);

  const handleEvent = useCallback((event: AiEvent) => {
    switch (event.type) {
      case 'welcome':
        setStatus('connected');
        if (event.session_id) setActiveSessionId(event.session_id);
        break;
      case 'typing':
        setIsTyping(true);
        streamBufRef.current = '';
        streamIdRef.current = crypto.randomUUID();
        streamToolsRef.current = [];
        setMessages((prev) => ([
          ...prev,
          { id: streamIdRef.current, role: 'assistant', blocks: [], timestamp: new Date(), toolsUsed: [] },
        ]));
        break;
      case 'token': {
        const chunk = event.content ?? event.message ?? '';
        if (chunk) {
          streamBufRef.current += chunk;
          const blocks = parseBlocks(streamBufRef.current);
          const msgId = streamIdRef.current;
          setMessages((prev) => prev.map((message) => (message.id === msgId ? { ...message, blocks } : message)));
        }
        break;
      }
      case 'tool_use':
        setToolInProgress(event.name ?? null);
        if (event.name) streamToolsRef.current = [...streamToolsRef.current, event.name];
        break;
      case 'done': {
        setIsTyping(false);
        setToolInProgress(null);
        const tools = streamToolsRef.current;
        const msgId = streamIdRef.current;
        if (tools.length > 0) {
          setMessages((prev) => prev.map((message) => (message.id === msgId ? { ...message, toolsUsed: tools } : message)));
        }
        streamBufRef.current = '';
        streamIdRef.current = '';
        streamToolsRef.current = [];
        void refreshSessions(activeSessionId);
        break;
      }
      case 'error':
        setIsTyping(false);
        setToolInProgress(null);
        setMessages((prev) => ([
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            blocks: [{ kind: 'text', content: `⚠️ ${event.message ?? 'Eroare necunoscută'}` }],
            timestamp: new Date(),
          },
        ]));
        break;
      case 'bridge_offline':
        setStatus('offline');
        setIsTyping(false);
        setToolInProgress(null);
        break;
    }
  }, [activeSessionId, refreshSessions]);

  useEffect(() => {
    void loadInitialState();
    return () => wsRef.current?.disconnect();
  }, [loadInitialState]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || !wsRef.current?.isConnected || isTyping || !activeSessionId) return;

    const effectiveText = text || (attachments.length > 0 ? 'Am atasat fisiere pentru analiza.' : '');
    setMessages((prev) => ([
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'user',
        blocks: [{ kind: 'text', content: effectiveText }],
        timestamp: new Date(),
        attachments,
      },
    ]));
    wsRef.current.send(effectiveText, attachments);
    setInput('');
    setAttachments([]);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const autoResize = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    event.target.style.height = 'auto';
    event.target.style.height = `${Math.min(event.target.scrollHeight, 132)}px`;
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const handleFilesSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    setUploading(true);
    try {
      const uploaded = await Promise.all(files.map((file) => uploadAiAttachment(file)));
      setAttachments((prev) => [...prev, ...uploaded]);
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const removeAttachment = (path: string) => {
    setAttachments((prev) => prev.filter((item) => item.path !== path));
  };

  const handleNewSession = async () => {
    const detail = await createAiSession(deviceId);
    setMessages([]);
    setAttachments([]);
    setInput('');
    setActiveSessionId(detail.session.id);
    await refreshSessions(detail.session.id);
    reconnectSocket(detail.session.id);
    setSessionDrawerOpen(false);
  };

  const handleActivateSession = async (sessionId: string) => {
    if (sessionId === activeSessionId) {
      setSessionDrawerOpen(false);
      return;
    }
    const detail = await activateAiSession(sessionId, deviceId);
    setMessages(normalizeMessages(detail.messages));
    setAttachments([]);
    setInput('');
    setActiveSessionId(sessionId);
    await refreshSessions(sessionId);
    reconnectSocket(sessionId);
    setSessionDrawerOpen(false);
  };

  const statusDot = {
    connected: 'bg-emerald-500',
    connecting: 'bg-amber-400 animate-pulse',
    disconnected: 'bg-slate-400',
    offline: 'bg-red-500',
  }[status];

  const statusLabel = {
    connected: 'UniAI activ',
    connecting: 'Se conecteaza...',
    disconnected: 'Reconectare...',
    offline: 'Offline',
  }[status];

  const canSend = wsRef.current?.isConnected && !isTyping && !uploading && (input.trim().length > 0 || attachments.length > 0);

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-transparent dark:bg-transparent">
      <aside className={cn(
        'absolute inset-y-0 left-0 z-20 w-80 border-r border-slate-200 bg-white/95 p-4 shadow-2xl transition-transform dark:border-slate-800 dark:bg-slate-950/95',
        sessionDrawerOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Sesiuni</p>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Istoric UniAI</p>
          </div>
          <button onClick={() => setSessionDrawerOpen(false)} className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={16} />
          </button>
        </div>
        <button onClick={handleNewSession} className="mb-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-700">
          <PlusSquare size={16} /> Chat nou
        </button>
        <div className="space-y-2 overflow-y-auto pr-1">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => void handleActivateSession(session.id)}
              className={cn(
                'w-full rounded-2xl border px-3 py-3 text-left transition-colors',
                session.is_active
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-100'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold">{session.title}</p>
                {session.is_active && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-800/50 dark:text-emerald-200">activ</span>}
              </div>
              <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{session.preview || 'Sesiune fara preview inca.'}</p>
              <p className="mt-2 text-[11px] text-slate-400">{formatSessionTime(session.updated_at)}</p>
            </button>
          ))}
        </div>
      </aside>

      {sessionDrawerOpen && <div className="absolute inset-0 z-10 bg-slate-900/30 backdrop-blur-sm" onClick={() => setSessionDrawerOpen(false)} />}

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden pb-2">
        <div className="px-4 pb-3 pt-6">
          <div className="flex items-center gap-3">
            <button onClick={() => setSessionDrawerOpen(true)} className="rounded-2xl border border-slate-200 bg-white p-2 text-slate-600 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
              <Menu size={16} />
            </button>
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-lg shadow-emerald-600/25">
              <Bot size={17} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">UniAI</span>
                <span className={cn('h-2 w-2 rounded-full', statusDot)} />
              </div>
              <p className="text-[11px] text-slate-500">{statusLabel}</p>
            </div>
            <button onClick={handleNewSession} className="ml-auto rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
              Chat nou
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          {status === 'offline' && (
            <div className="flex flex-col items-center gap-2 py-10 text-slate-400">
              <WifiOff size={28} />
              <p className="text-[13px]">UniAI nu este disponibil momentan.</p>
            </div>
          )}

          {loadingSession ? (
            <div className="py-10 text-center text-sm text-slate-500">Incarc sesiunea curenta...</div>
          ) : (
            <div className="space-y-3">
              {messages.map((message) => (
                <div key={message.id} className={cn('flex gap-2', message.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
                  <div className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl',
                    message.role === 'assistant' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200' : 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200'
                  )}>
                    {message.role === 'assistant' ? <Bot size={15} /> : <User size={15} />}
                  </div>
                  <div className={cn(
                    'max-w-[84%] rounded-[24px] px-4 py-3 text-[13px] leading-relaxed shadow-sm',
                    message.role === 'assistant' ? 'bg-white text-slate-800 dark:bg-slate-900 dark:text-slate-100' : 'bg-emerald-600 text-white'
                  )}>
                    {message.blocks.map((block, index) => (
                      block.kind === 'chart' ? (
                        <ChartBlock key={index} spec={block.spec} />
                      ) : (
                        <div key={index} className="prose prose-sm max-w-none prose-slate dark:prose-invert">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
                        </div>
                      )
                    ))}
                    {(message.attachments?.length ?? 0) > 0 && (
                      <div className="mt-3 space-y-2">
                        {message.attachments!.map((file) => (
                          <div key={file.path} className={cn(
                            'flex items-center gap-2 rounded-2xl px-3 py-2 text-xs',
                            message.role === 'assistant' ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' : 'bg-emerald-500/40 text-emerald-50'
                          )}>
                            <FileText size={14} />
                            <span className="truncate">{attachmentLabel(file)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {(message.toolsUsed?.length ?? 0) > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {message.toolsUsed!.map((tool) => (
                          <span key={tool} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                            <Database size={10} /> {tool}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className={cn('mt-2 text-[10px]', message.role === 'assistant' ? 'text-slate-400' : 'text-emerald-100')}>{formatTime(message.timestamp)}</p>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex gap-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">
                    <Bot size={15} />
                  </div>
                  <div className="rounded-[24px] bg-white px-4 py-3 shadow-sm dark:bg-slate-900">
                    {toolInProgress ? (
                      <span className="flex items-center gap-2 text-[11px] text-slate-500"><Database size={11} className="animate-pulse" /> {toolInProgress}...</span>
                    ) : (
                      <div className="flex gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
                      </div>
                    )}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="bg-transparent px-4 pb-5 pt-3">
          {attachments.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {attachments.map((file) => (
                <div key={file.path} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                  <FileText size={14} />
                  <span className="max-w-48 truncate">{attachmentLabel(file)}</span>
                  <button onClick={() => removeAttachment(file.path)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-100">
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2 rounded-[28px] border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
            <button onClick={() => setSessionDrawerOpen(true)} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              <Menu size={18} />
            </button>
            <button onClick={() => fileInputRef.current?.click()} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              <Paperclip size={18} />
            </button>
            <input ref={fileInputRef} type="file" multiple className="hidden" accept="image/*,.pdf,.md,.txt,.docx,.xlsx,.pptx" onChange={handleFilesSelected} />
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={autoResize}
              onKeyDown={handleKeyDown}
              disabled={status !== 'connected' || isTyping || loadingSession}
              placeholder=""
              className="max-h-32 flex-1 resize-none bg-transparent px-1 py-2 text-[13px] outline-none placeholder:text-slate-400 dark:text-slate-100"
            />
            <button
              onClick={sendMessage}
              disabled={!canSend}
              className={cn(
                'flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl transition-all',
                canSend ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/25 hover:bg-emerald-700' : 'bg-slate-100 text-slate-400 dark:bg-slate-800'
              )}
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
