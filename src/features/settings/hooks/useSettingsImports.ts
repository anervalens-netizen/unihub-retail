import { useCallback, useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getImportHistory } from "../../../api/imports";
import { queryKeys } from "../../../lib/queryKeys";
import type { ImportsModel } from "../types";
import {
  useErpReconciliationImport,
  usePromoActualsImport,
} from "./useAuxiliaryImports";
import { useSalesImport } from "./useSalesImport";

const CACHE_TTL_MS = 5 * 60 * 1000;

export function useSettingsImports(
  enabled: boolean,
  onImportCompleted: (month: string) => void,
  identityKey = "anonymous",
  authorized = enabled,
): ImportsModel {
  const queryClient = useQueryClient();
  const historyKey = useMemo(() => queryKeys.settings.imports(identityKey), [identityKey]);
  const historyQuery = useQuery({
    queryKey: historyKey,
    enabled,
    queryFn: ({ signal }) => getImportHistory(signal),
    staleTime: CACHE_TTL_MS,
    retry: 1,
  });
  const history = useMemo(() => historyQuery.data ?? [], [historyQuery.data]);
  const erp = useErpReconciliationImport();
  const promo = usePromoActualsImport();
  const refreshHistory = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: historyKey, exact: true });
    await queryClient.fetchQuery({
      queryKey: historyKey,
      queryFn: ({ signal }) => getImportHistory(signal),
      staleTime: 0,
    });
  }, [historyKey, queryClient]);
  const sales = useSalesImport({
    refreshHistory,
    onImportCompleted,
    setErpReconciliationMonth: erp.setErpReconciliationMonth,
  });
  useEffect(() => {
    if (!authorized) {
      void queryClient.removeQueries({ queryKey: historyKey, exact: true });
      return;
    }
    if (enabled && historyQuery.isError) {
      sales.setMessage("Nu am putut încărca istoricul importurilor.");
      sales.setMessageType("error");
    }
  }, [authorized, enabled, historyKey, historyQuery.isError, queryClient, sales]);
  const erpReconciliationMonths = useMemo(
    () => Array.from(new Set(
      history.filter((entry) => entry.status === "completed").map((entry) => entry.import_month),
    )).sort((a, b) => b.localeCompare(a)),
    [history],
  );
  useEffect(() => {
    erp.setErpReconciliationMonth((current) =>
      erpReconciliationMonths.includes(current) ? current : (erpReconciliationMonths[0] ?? ""),
    );
  }, [erp, erpReconciliationMonths]);
  return { history, ...sales, ...erp, erpReconciliationMonths, ...promo };
}
