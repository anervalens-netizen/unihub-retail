import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MAX_DASHBOARD_BATCH_MONTHS } from "../../api/dashboard";
import * as dashboardPresenters from "./presenters";
import type { DashboardSection } from "./dashboardTypes";

interface UseDashboardHistorySelectionArgs {
  currentMonth: string;
  months: string[];
  initialSection: DashboardSection;
}

/** Owns the history picker state so the Dashboard page stays an orchestration layer. */
export function useDashboardHistorySelection({
  currentMonth,
  months,
  initialSection,
}: UseDashboardHistorySelectionArgs) {
  const defaultHistoryMonth = dashboardPresenters.getDefaultHistoryMonth(
    currentMonth,
    months,
  );
  const [activeSection, setActiveSection] =
    useState<DashboardSection>(initialSection);
  const [historyMonth, setHistoryMonth] = useState(defaultHistoryMonth);
  const [historyMonths, setHistoryMonths] = useState<string[]>([
    defaultHistoryMonth,
  ]);
  const [draftHistoryMonths, setDraftHistoryMonths] = useState<string[]>([
    defaultHistoryMonth,
  ]);
  const [historyMonthDropdownOpen, setHistoryMonthDropdownOpen] =
    useState(false);
  const historyMonthDropdownRef = useRef<HTMLDetailsElement>(null);
  const historySelectionTouchedRef = useRef(false);
  const historySelectionCurrentMonthRef = useRef(currentMonth);

  useEffect(() => {
    const currentMonthChanged =
      historySelectionCurrentMonthRef.current !== currentMonth;
    if (currentMonthChanged) {
      historySelectionCurrentMonthRef.current = currentMonth;
      historySelectionTouchedRef.current = false;
    }

    if (!historySelectionTouchedRef.current) {
      setHistoryMonth(defaultHistoryMonth);
      setHistoryMonths([defaultHistoryMonth]);
      setDraftHistoryMonths([defaultHistoryMonth]);
      return;
    }

    setHistoryMonth((previous) =>
      months.includes(previous) ? previous : defaultHistoryMonth,
    );
    setHistoryMonths((previous) => {
      const valid = previous.filter((month) => months.includes(month));
      return valid.length > 0 ? valid : [defaultHistoryMonth];
    });
    setDraftHistoryMonths((previous) => {
      const valid = previous.filter((month) => months.includes(month));
      return valid.length > 0 ? valid : [defaultHistoryMonth];
    });
  }, [months, currentMonth, defaultHistoryMonth]);

  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

  const selectedHistoryMonths = useMemo(() => {
    const valid = historyMonths.filter((month) => months.includes(month));
    return dashboardPresenters.sortMonthsAsc(
      valid.length > 0 ? valid : [historyMonth],
    );
  }, [historyMonth, historyMonths, months]);
  const historySelectionLabel = useMemo(
    () => dashboardPresenters.formatMonthSelectionLabel(selectedHistoryMonths),
    [selectedHistoryMonths],
  );
  const historySelectionSlug = useMemo(
    () => selectedHistoryMonths.join("_"),
    [selectedHistoryMonths],
  );
  const draftSelectedHistoryMonths = useMemo(() => {
    const valid = draftHistoryMonths.filter((month) => months.includes(month));
    return dashboardPresenters.sortMonthsAsc(
      valid.length > 0 ? valid : selectedHistoryMonths,
    );
  }, [draftHistoryMonths, months, selectedHistoryMonths]);
  const draftHistorySelectionLabel = useMemo(
    () =>
      dashboardPresenters.formatMonthSelectionLabel(draftSelectedHistoryMonths),
    [draftSelectedHistoryMonths],
  );

  const handleToggleHistoryMonth = useCallback(
    (month: string) => {
      const isSelected = draftSelectedHistoryMonths.includes(month);
      if (isSelected && draftSelectedHistoryMonths.length === 1) return;
      if (
        !isSelected &&
        draftSelectedHistoryMonths.length >= MAX_DASHBOARD_BATCH_MONTHS
      )
        return;
      const next = isSelected
        ? draftSelectedHistoryMonths.filter((item) => item !== month)
        : [...draftSelectedHistoryMonths, month];
      setDraftHistoryMonths(dashboardPresenters.sortMonthsAsc(next));
    },
    [draftSelectedHistoryMonths],
  );

  const handleApplyHistoryMonths = useCallback(() => {
    const sorted = dashboardPresenters.sortMonthsAsc(draftHistoryMonths);
    historySelectionTouchedRef.current = true;
    setHistoryMonths(sorted);
    setHistoryMonth(sorted[sorted.length - 1] ?? currentMonth);
    historyMonthDropdownRef.current?.removeAttribute("open");
  }, [currentMonth, draftHistoryMonths]);

  const handleApplyHistoryPreset = useCallback(
    (count: number) => {
      const selected = dashboardPresenters.sortMonthsAsc(
        months.slice(0, Math.min(count, MAX_DASHBOARD_BATCH_MONTHS)),
      );
      if (selected.length === 0) return;
      historySelectionTouchedRef.current = true;
      setDraftHistoryMonths(selected);
      setHistoryMonths(selected);
      setHistoryMonth(selected[selected.length - 1] ?? currentMonth);
      historyMonthDropdownRef.current?.removeAttribute("open");
    },
    [currentMonth, months],
  );

  const handleHistoryDropdownToggle = useCallback(() => {
    const isOpen = Boolean(historyMonthDropdownRef.current?.open);
    setHistoryMonthDropdownOpen(isOpen);
    if (isOpen) setDraftHistoryMonths(selectedHistoryMonths);
  }, [selectedHistoryMonths]);

  return {
    activeSection,
    setActiveSection,
    historyMonth,
    selectedHistoryMonths,
    historySelectionLabel,
    historySelectionSlug,
    draftSelectedHistoryMonths,
    draftHistorySelectionLabel,
    historyMonthDropdownOpen,
    historyMonthDropdownRef,
    handleToggleHistoryMonth,
    handleApplyHistoryMonths,
    handleApplyHistoryPreset,
    handleHistoryDropdownToggle,
  };
}
