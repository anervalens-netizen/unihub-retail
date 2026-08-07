interface RefreshStatusErrorProps {
  error: unknown;
  compact?: boolean;
}

const fallback = 'Starea verificării nu poate fi confirmată.';

export function RefreshStatusError({ error, compact = false }: RefreshStatusErrorProps) {
  const message = error instanceof Error ? error.message : fallback;
  if (compact) {
    return (
      <span
        className="flex-shrink-0 text-[10px] text-rose-500"
        title={message}
        aria-label={fallback}
      >
        status necunoscut
      </span>
    );
  }
  return (
    <div className="mt-1 text-[10px] text-rose-500" role="alert">
      {message}
    </div>
  );
}
