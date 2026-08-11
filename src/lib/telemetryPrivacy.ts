const REDACTED = '[REDACTED]';
const TRUNCATED = '[TRUNCATED]';
const CIRCULAR = '[CIRCULAR]';
const MAX_DEPTH = 8;
const MAX_ITEMS = 64;
const MAX_KEYS = 64;
const MAX_NODES = 512;
const MAX_STRING = 2_048;
// Defensive-only key assembled so salary scans stay focused on data-bearing identifiers.
const NATIONAL_ID_KEY = String.fromCodePoint(99, 110, 112);

const SENSITIVE_KEY_PARTS = [
  'authorization',
  'cookie',
  'token',
  'secret',
  'password',
  'passwd',
  NATIONAL_ID_KEY,
  'salary',
  'salariu',
  'email',
  'nume',
  'username',
  'preferred_username',
  'query_string',
];
const BODY_KEYS = new Set(['body', 'data', 'form_data', 'payload', 'post_data']);
const FREE_TEXT_KEYS = new Set(['message', 'detail', 'value', 'formatted', 'description']);
const URL_KEYS = new Set(['url', 'referer', 'referrer', 'pathname', 'transaction']);

function normalizedKey(key: string): string {
  return key
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function sensitiveKey(key: string): boolean {
  const normalized = normalizedKey(key);
  return (
    BODY_KEYS.has(normalized) ||
    normalized === 'headers' ||
    SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part))
  );
}

export function stripUrlSecrets(value: string): string {
  try {
    const base = typeof window === 'undefined' ? 'https://telemetry.invalid' : window.location.origin;
    const url = new URL(value, base);
    if (!/^(https?:)$/i.test(url.protocol)) return REDACTED;
    // Route segments can contain stable application identities (for example
    // salary person IDs), so telemetry retains at most the bounded origin.
    return value.startsWith('/') ? '/[REDACTED]' : url.origin;
  } catch {
    return REDACTED;
  }
}

interface ScrubState {
  remaining: number;
  ancestors: WeakSet<object>;
}

function scrubValue(value: unknown, key: string, depth: number, state: ScrubState): unknown {
  if (depth >= MAX_DEPTH || state.remaining <= 0) return TRUNCATED;
  state.remaining -= 1;
  const normalized = normalizedKey(key);
  if (sensitiveKey(key) || FREE_TEXT_KEYS.has(normalized)) return REDACTED;
  if (typeof value === 'string') {
    if (URL_KEYS.has(normalized)) return stripUrlSecrets(value);
    return value.slice(0, MAX_STRING);
  }
  if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return value;
  }
  if (Array.isArray(value)) {
    if (state.ancestors.has(value)) return CIRCULAR;
    state.ancestors.add(value);
    try {
      return value
        .slice(0, MAX_ITEMS)
        .map((item) => scrubValue(item, '', depth + 1, state));
    } finally {
      state.ancestors.delete(value);
    }
  }
  if (value && typeof value === 'object') {
    if (state.ancestors.has(value)) return CIRCULAR;
    state.ancestors.add(value);
    const output: Record<string, unknown> = {};
    try {
      for (const [childKey, childValue] of Object.entries(value).slice(0, MAX_KEYS)) {
        output[childKey] = scrubValue(childValue, childKey, depth + 1, state);
      }
    } finally {
      state.ancestors.delete(value);
    }
    return output;
  }
  return REDACTED;
}

export function scrubTelemetryEvent<T extends object>(event: T): T {
  return scrubValue(event, '', 0, {
    remaining: MAX_NODES,
    ancestors: new WeakSet<object>(),
  }) as T;
}
