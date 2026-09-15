import type { RetailContextUrlState } from '../../lib/insightDeepLink';

export type AiReasoningEffort = 'none' | 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export type AiMessageRole = 'user' | 'assistant' | 'system';

export type AiMessageStatus = 'complete' | 'streaming' | 'error';

export interface AiArtifactAttachment {
  id: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  kind: 'input' | 'output';
  downloadUrl?: string;
}

export interface AiChatMessage {
  id: string;
  role: AiMessageRole;
  text: string;
  status: AiMessageStatus;
  createdAt: string;
  attachments?: AiArtifactAttachment[];
}

export interface AiConversation {
  id: string;
  title: string;
  effort: AiReasoningEffort;
  createdAt: string;
  updatedAt: string;
}

export interface AiCurrentViewContext {
  retail: RetailContextUrlState | null;
  locationHref: string;
}

export interface AiComposerSubmission {
  text: string;
  effort: AiReasoningEffort;
  includeCurrentView: boolean;
  currentView: AiCurrentViewContext | null;
  files: File[];
  mode: 'send' | 'steer';
}

export type AiRunStatus = 'idle' | 'running' | 'stopping' | 'unavailable';
