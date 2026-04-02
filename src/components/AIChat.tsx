import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, Database, RefreshCw, Send, User, Wifi, WifiOff } from 'lucide-react';
import { cn } from '../lib/utils';
import { AiWebSocket, type AiEvent } from '../api/ai';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'offline';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CHART_COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#10b981', '#f43f5e', '#8b5cf6'];

function formatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Parse assistant text into blocks: plain text segments and ```chart``` blocks.
 */
function parseBlocks(text: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  const chartRegex = /```chart\n([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = chartRegex.exec(text)) !== null) {
    if (match.index > last) {
      const t = text.slice(last, match.index).trim();
      if (t) blocks.push({ kind: 'text', content: t });
    }
    try {
      const spec = JSON.parse(match[1]) as ChartSpec;
      blocks.push({ kind: 'chart', spec });
    } catch {
      blocks.push({ kind: 'text', content: match[0] });
    }
    last = match.index + match[0].length;
  }

  const remaining = text.slice(last).trim();
  if (remaining) blocks.push({ kind: 'text', content: remaining });

  return blocks.length > 0 ? blocks : [{ kind: 'text', content: text }];
}

// ---------------------------------------------------------------------------
// Chart renderer
// ---------------------------------------------------------------------------

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
    const pieKey = keys[0] ?? 'value';
    chart = (
      <PieChart>
        <Pie data={spec.data} dataKey={pieKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={80} label>
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
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((k, i) => (
          <Line key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]} dot={false} strokeWidth={2} />
        ))}
      </LineChart>
    );
  } else if (spec.chartType === 'area') {
    chart = (
      <AreaChart {...common}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((k, i) => (
          <Area key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]}
            fill={colors[i % colors.length] + '33'} strokeWidth={2} />
        ))}
      </AreaChart>
    );
  } else {
    // bar (default)
    chart = (
      <BarChart {...common}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={colors[i % colors.length]} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    );
  }

  return (
    <div className="mt-2 rounded-xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
      {spec.title && (
        <p className="mb-2 text-[11px] font-semibold text-slate-500 uppercase tracking-wide dark:text-slate-400">
          {spec.title}
        </p>
      )}
      <ResponsiveContainer width="100%" height={220}>
        {chart as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AIChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [toolInProgress, setToolInProgress] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wsRef = useRef<AiWebSocket | null>(null);

  // Streaming buffer for current assistant message
  const streamBufRef = useRef('');
  const streamIdRef = useRef('');
  const streamToolsRef = useRef<string[]>([]);

  // ---------------------------------------------------------------------------
  // WebSocket lifecycle
  // ---------------------------------------------------------------------------

  const handleEvent = useCallback((event: AiEvent) => {
    switch (event.type) {
      case 'welcome':
        setStatus('connected');
        if (event.message) {
          setMessages([{
            id: 'welcome',
            role: 'assistant',
            blocks: [{ kind: 'text', content: event.message }],
            timestamp: new Date(),
          }]);
        }
        break;

      case 'typing':
        setIsTyping(true);
        streamBufRef.current = '';
        streamIdRef.current = crypto.randomUUID();
        streamToolsRef.current = [];
        // Create empty assistant message placeholder
        setMessages((prev) => [
          ...prev,
          {
            id: streamIdRef.current,
            role: 'assistant',
            blocks: [],
            timestamp: new Date(),
            toolsUsed: [],
          },
        ]);
        break;

      case 'token':
        if (event.content) {
          streamBufRef.current += event.content;
          const blocks = parseBlocks(streamBufRef.current);
          const msgId = streamIdRef.current;
          setMessages((prev) =>
            prev.map((m) => (m.id === msgId ? { ...m, blocks } : m))
          );
        }
        break;

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
          setMessages((prev) =>
            prev.map((m) => (m.id === msgId ? { ...m, toolsUsed: tools } : m))
          );
        }
        streamBufRef.current = '';
        streamIdRef.current = '';
        streamToolsRef.current = [];
        break;
      }

      case 'error':
        setIsTyping(false);
        setToolInProgress(null);
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            blocks: [{ kind: 'text', content: `⚠️ ${event.message ?? 'Eroare necunoscută'}` }],
            timestamp: new Date(),
          },
        ]);
        break;

      case 'bridge_offline':
        setStatus('offline');
        setIsTyping(false);
        setToolInProgress(null);
        break;
    }
  }, []);

  const handleClose = useCallback(() => {
    setStatus((s) => (s === 'offline' ? 'offline' : 'disconnected'));
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('unihub_token') ?? '';
    if (!token) return;

    const ws = new AiWebSocket(token, handleEvent, handleClose);
    wsRef.current = ws;
    setStatus('connecting');
    ws.connect();

    return () => {
      ws.disconnect();
    };
  }, [handleEvent, handleClose]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // ---------------------------------------------------------------------------
  // Send message
  // ---------------------------------------------------------------------------

  const sendMessage = () => {
    const text = input.trim();
    if (!text || !wsRef.current?.isConnected || isTyping) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      blocks: [{ kind: 'text', content: text }],
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    wsRef.current.send(text);
  };

  const resetConversation = () => {
    wsRef.current?.resetSession();
    setMessages([]);
    streamBufRef.current = '';
    streamIdRef.current = '';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const autoResize = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  // ---------------------------------------------------------------------------
  // Status UI
  // ---------------------------------------------------------------------------

  const statusDot = {
    connected: 'bg-emerald-400',
    connecting: 'bg-amber-400 animate-pulse',
    disconnected: 'bg-slate-400',
    offline: 'bg-red-400',
  }[status];

  const statusLabel = {
    connected: 'UniAI activ',
    connecting: 'Se conectează...',
    disconnected: 'Reconectare...',
    offline: 'Offline',
  }[status];

  const canSend = wsRef.current?.isConnected && !isTyping && input.trim().length > 0;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="px-4 pt-7 pb-3">
        <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500">
          UniHub
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-indigo-600 text-white">
            <Bot size={15} />
          </div>
          <div>
            <span className="text-sm font-semibold">UniAI</span>
            <span className="ml-1.5 text-[10px] text-slate-400">Analist vânzări</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={resetConversation}
              title="Conversație nouă"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700"
            >
              <RefreshCw size={13} />
            </button>
            <span className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-400">
              <span className={cn('h-1.5 w-1.5 rounded-full', statusDot)} />
              {statusLabel}
            </span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
        {status === 'offline' && (
          <div className="flex flex-col items-center gap-2 py-8 text-slate-400">
            <WifiOff size={28} />
            <p className="text-[13px]">UniAI nu este disponibil momentan.</p>
            <p className="text-[11px]">Verifică dacă serviciul hermes-unihub-bridge rulează.</p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn('flex gap-2', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
          >
            {/* Avatar */}
            <div
              className={cn(
                'flex h-7 w-7 shrink-0 items-center justify-center rounded-xl',
                msg.role === 'assistant'
                  ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400'
                  : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
              )}
            >
              {msg.role === 'assistant' ? <Bot size={14} /> : <User size={14} />}
            </div>

            {/* Bubble */}
            <div
              className={cn(
                'max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed',
                msg.role === 'assistant'
                  ? 'bg-white text-slate-800 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                  : 'bg-indigo-600 text-white'
              )}
            >
              {msg.role === 'assistant' ? (
                <>
                  {msg.blocks.map((block, i) =>
                    block.kind === 'chart' ? (
                      <ChartBlock key={i} spec={block.spec} />
                    ) : (
                      <div key={i} className="prose prose-sm prose-slate dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {block.content}
                        </ReactMarkdown>
                      </div>
                    )
                  )}
                  {/* Tool badges */}
                  {(msg.toolsUsed?.length ?? 0) > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {msg.toolsUsed!.map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700 dark:text-slate-400"
                        >
                          <Database size={9} />
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="whitespace-pre-wrap">
                  {msg.blocks[0]?.kind === 'text' ? msg.blocks[0].content : ''}
                </p>
              )}
              <p
                className={cn(
                  'mt-1 text-[10px]',
                  msg.role === 'assistant'
                    ? 'text-slate-400 dark:text-slate-500'
                    : 'text-indigo-200'
                )}
              >
                {formatTime(msg.timestamp)}
              </p>
            </div>
          </div>
        ))}

        {/* Typing / tool indicator */}
        {isTyping && (
          <div className="flex gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400">
              <Bot size={14} />
            </div>
            <div className="flex items-center gap-2 rounded-2xl bg-white px-3.5 py-2.5 shadow-sm dark:bg-slate-800">
              {toolInProgress ? (
                <span className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                  <Database size={11} className="animate-pulse" />
                  {toolInProgress === 'query_database'
                    ? 'Interoghez baza de date...'
                    : toolInProgress === 'get_db_schema'
                    ? 'Citesc schema DB...'
                    : toolInProgress === 'search_management'
                    ? 'Caut resurse...'
                    : `${toolInProgress}...`}
                </span>
              ) : (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
                </>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-28 pt-2">
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={autoResize}
            onKeyDown={handleKeyDown}
            placeholder={
              status === 'connected'
                ? 'Întreabă ceva despre vânzări, magazine, agenți...'
                : 'UniAI nu este conectat...'
            }
            disabled={status !== 'connected' || isTyping}
            className="flex-1 resize-none bg-transparent text-[13px] outline-none placeholder:text-slate-400 dark:text-slate-100 disabled:opacity-50"
            style={{ maxHeight: 120 }}
          />
          <button
            onClick={sendMessage}
            disabled={!canSend}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-all',
              canSend
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/30 hover:bg-indigo-700'
                : 'bg-slate-100 text-slate-400 dark:bg-slate-700'
            )}
          >
            <Send size={14} />
          </button>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-slate-400">
          Enter trimite · Shift+Enter linie nouă
        </p>
      </div>
    </div>
  );
}
