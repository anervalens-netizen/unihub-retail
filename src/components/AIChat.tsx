import React, { useEffect, useRef, useState } from 'react';
import { Bot, Send, User } from 'lucide-react';
import { cn } from '../lib/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

export default function AIChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Salut! Sunt asistentul AI UniHub. Cum te pot ajuta?',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setIsTyping(true);

    // TODO: replace with real agent call
    await new Promise((resolve) => setTimeout(resolve, 900));
    setIsTyping(false);

    const botMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: 'Agentul AI nu este conectat încă. Voi fi disponibil în curând.',
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, botMsg]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const autoResize = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

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
          <span className="text-sm font-semibold">Asistent AI</span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-semibold text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Neconectat
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
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
                'max-w-[75%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed',
                msg.role === 'assistant'
                  ? 'bg-white text-slate-800 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                  : 'bg-indigo-600 text-white'
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
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

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400">
              <Bot size={14} />
            </div>
            <div className="flex items-center gap-1 rounded-2xl bg-white px-3.5 py-3 shadow-sm dark:bg-slate-800">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
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
            placeholder="Scrie un mesaj..."
            className="flex-1 resize-none bg-transparent text-[13px] outline-none placeholder:text-slate-400 dark:text-slate-100"
            style={{ maxHeight: 120 }}
          />
          <button
            onClick={() => void sendMessage()}
            disabled={!input.trim()}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-all',
              input.trim()
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
