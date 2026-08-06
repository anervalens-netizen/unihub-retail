// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getImportHistory: vi.fn(),
  getImportJobStatus: vi.fn(),
  promoteSalesGeneration: vi.fn(),
  uploadErpReconciliationFile: vi.fn(),
  uploadPromoActualsFile: vi.fn(),
  uploadSalesFile: vi.fn(),
}));

vi.mock("../../../api/imports", () => api);

import { useSettingsImports } from "./useSettingsImports";

function wrapper(client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
})) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useSettingsImports request ownership", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getImportHistory.mockResolvedValue([]);
  });

  it("does not fetch in an inactive tab, then fetches once and keeps the identity cache", async () => {
    const { rerender } = renderHook(
      ({ enabled, identityKey }) =>
        useSettingsImports(enabled, vi.fn(), identityKey, true),
      {
        initialProps: { enabled: false, identityKey: "user-a" },
        wrapper: wrapper(),
      },
    );

    expect(api.getImportHistory).not.toHaveBeenCalled();
    rerender({ enabled: true, identityKey: "user-a" });
    await waitFor(() => expect(api.getImportHistory).toHaveBeenCalledTimes(1));

    rerender({ enabled: false, identityKey: "user-a" });
    rerender({ enabled: true, identityKey: "user-a" });
    await waitFor(() => expect(api.getImportHistory).toHaveBeenCalledTimes(1));
  });

  it("isolates identities and removes cached history on permission revocation", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    const { rerender } = renderHook(
      ({ identityKey, authorized }) =>
        useSettingsImports(true, vi.fn(), identityKey, authorized),
      {
        initialProps: { identityKey: "user-a", authorized: true },
        wrapper: wrapper(client),
      },
    );
    await waitFor(() => expect(api.getImportHistory).toHaveBeenCalledTimes(1));

    rerender({ identityKey: "user-b", authorized: true });
    await waitFor(() => expect(api.getImportHistory).toHaveBeenCalledTimes(2));

    rerender({ identityKey: "user-a", authorized: false });
    await waitFor(() =>
      expect(client.getQueryData(["settings", "user-a", "imports"])).toBeUndefined(),
    );
  });
});
