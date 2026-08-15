import { getImportJobStatus } from "../../../api/imports";

export const IMPORT_POLL_OPTIONS = {
  intervalMs: 1500,
  // Fereastră UI maximă 30 min; rezultatele ARQ sunt păstrate minimum 60 min.
  maxAttempts: 1200,
  maxConsecutiveErrors: 20,
  getStatus: getImportJobStatus,
};

