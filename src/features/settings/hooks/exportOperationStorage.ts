const key = (identityKey: string) =>
  `unihub:settings:export-operation:${identityKey}`;

export function readStoredExportOperationId(identityKey: string): number | null {
  if (typeof window === "undefined") return null;
  const value = Number(window.sessionStorage.getItem(key(identityKey)));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function storeExportOperationId(identityKey: string, operationId: number) {
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(key(identityKey), String(operationId));
  }
}

export function clearStoredExportOperationId(identityKey: string) {
  if (typeof window !== "undefined") window.sessionStorage.removeItem(key(identityKey));
}

