import { useEffect, useState } from "react";
import { getPerformanceDetail } from "../../api/dashboard";
import type { PerformanceDetailResponse } from "../../api/generated/runtime-types";
import type { PerformanceSelection } from "./PerformanceDetailDrawer";

interface PerformanceDetailOptions {
  currentMonth: string;
  firma: string;
}

export function useDashboardPerformanceDetail({
  currentMonth,
  firma,
}: PerformanceDetailOptions) {
  const [selection, setSelection] = useState<PerformanceSelection | null>(null);
  const [detail, setDetail] = useState<PerformanceDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selection) {
      setDetail(null);
      setError("");
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError("");
    getPerformanceDetail({
      month: currentMonth,
      level: selection.level,
      key: selection.key,
      firma,
      site_code: selection.site_code,
      current_scope: true,
      include_closed_stores: false,
    })
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((errorValue: unknown) => {
        if (cancelled) return;
        const message =
          errorValue instanceof Error
            ? errorValue.message.replace(/^API error: \d+\s*-?\s*/i, "")
            : "";
        setError(message || "Detaliul nu a putut fi incarcat.");
        setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentMonth, firma, selection]);

  return {
    performanceSelection: selection,
    setPerformanceSelection: setSelection,
    performanceDetail: detail,
    performanceLoading: loading,
    performanceError: error,
  };
}
