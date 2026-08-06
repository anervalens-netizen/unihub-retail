import * as Sentry from "@sentry/react";

export type FrontendBootstrapFailureReason =
  | "session_expired"
  | "stale_cache"
  | "unavailable";

/** Emits one low-cardinality browser metric without user or business context. */
export function reportFrontendBootstrapFailure(
  reason: FrontendBootstrapFailureReason,
): void {
  Sentry.metrics.count("frontend_bootstrap_failure", 1, {
    attributes: { reason },
  });
}
