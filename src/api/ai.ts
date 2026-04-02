/**
 * UniAI WebSocket client.
 *
 * Connects to /api/ai/ws and handles the streaming chat protocol.
 */

export type AiEventType =
  | 'welcome'
  | 'typing'
  | 'token'
  | 'tool_use'
  | 'done'
  | 'error'
  | 'bridge_offline';

export interface AiEvent {
  type: AiEventType;
  content?: string;
  message?: string;
  name?: string;
  input?: string;
  session_id?: string;
}

export type AiEventHandler = (event: AiEvent) => void;

const resolveWsUrl = (): string => {
  const apiBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (apiBase) {
    const url = new URL(apiBase);
    const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${url.host}/api/ai/ws`;
  }
  // Same host as the page
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ai/ws`;
};

export class AiWebSocket {
  private ws: WebSocket | null = null;
  private onEvent: AiEventHandler;
  private onClose: () => void;
  private token: string;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(token: string, onEvent: AiEventHandler, onClose: () => void) {
    this.token = token;
    this.onEvent = onEvent;
    this.onClose = onClose;
  }

  connect(): void {
    this.closed = false;
    const url = `${resolveWsUrl()}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);

    this.ws.onmessage = (ev) => {
      try {
        const event: AiEvent = JSON.parse(ev.data as string);
        this.onEvent(event);
      } catch {
        // ignore malformed events
      }
    };

    this.ws.onclose = () => {
      if (!this.closed) {
        this.scheduleReconnect();
      }
      this.onClose();
    };

    this.ws.onerror = () => {
      // error will be followed by close
    };
  }

  send(message: string, reset = false): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'message', content: message, reset }));
    }
  }

  resetSession(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'message', content: '__reset__', reset: true }));
    }
  }

  disconnect(): void {
    this.closed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    this.reconnectTimer = setTimeout(() => {
      if (!this.closed) {
        this.connect();
      }
    }, 3000);
  }
}
