import { useCallback, useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';

import {
  calculateTargetScenario,
  downloadTargetScenario,
  fetchTargetScenario,
  finalizeTargetScenario,
  saveTargetFinalValues,
  type TargetCalculatorContext,
  type TargetScenario,
} from '../api';
import { ApiError, getApiErrorMessage } from '../../../api/client';
import { seasonalityYearsFromMode } from '../../../lib/targetSeasonality';
import type { SeasonalityMode } from '../../../components/SeasonalityControl';
import { recalculateVisibleScenario } from '../model';

type ActionsDeps = {
  context: TargetCalculatorContext | null;
  scenario: TargetScenario | null;
  regionalFilter: string;
  targetMonth: string;
  totalTarget: string;
  minFloor: string;
  seasonalityMode: SeasonalityMode;
  dirty: boolean;
  dirtyRows: Set<string>;
  savingRows: Set<string>;
  scenarioRef: MutableRefObject<TargetScenario | null>;
  dirtyRowsRef: MutableRefObject<Set<string>>;
  editVersionsRef: MutableRefObject<Map<string, number>>;
  replaceScenario: (next: TargetScenario | null) => void;
  clearLocalEdits: () => void;
  setRegionalFilter: Dispatch<SetStateAction<string>>;
  setSelectedLocationCodes: Dispatch<SetStateAction<string[]>>;
  setBusy: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setConflictRetryAvailable: Dispatch<SetStateAction<boolean>>;
  setDirtyRows: Dispatch<SetStateAction<Set<string>>>;
  setSavingRows: Dispatch<SetStateAction<Set<string>>>;
};

export function useTargetScenarioActions(deps: ActionsDeps) {
  const {
    context, scenario, regionalFilter, targetMonth, totalTarget, minFloor, seasonalityMode,
    dirty, dirtyRows, savingRows, scenarioRef, dirtyRowsRef, editVersionsRef,
    replaceScenario, clearLocalEdits, setRegionalFilter, setSelectedLocationCodes, setBusy, setError,
    setConflictRetryAvailable, setDirtyRows, setSavingRows,
  } = deps;

const toggleLocationFilter = (siteCode: string) => {
  if (!siteCode) return;
  setSelectedLocationCodes((current) => (
    current.includes(siteCode)
      ? current.filter((item) => item !== siteCode)
      : [...current, siteCode]
  ));
};

const removeLocationFilter = (siteCode: string) => {
  setSelectedLocationCodes((current) => current.filter((item) => item !== siteCode));
};

const handleCalculate = async () => {
  const parsedTarget = Number(totalTarget);
  const parsedFloor = Number(minFloor);
  if (seasonalityMode === null) {
    setError('Asteapta initializarea modului de sezonalitate.');
    return;
  }
  if (!targetMonth || parsedTarget <= 0 || parsedFloor < 0) {
    setError('Completeaza parametrii de calcul cu valori valide.');
    return;
  }
  const existingTarget = scenarioRef.current;
  const recalculatingCurrentDraft = existingTarget?.target_month === targetMonth && existingTarget.status === 'draft';
  if (existingTarget?.target_month === targetMonth && existingTarget.status === 'finalized') {
    setError('Targetul acestei luni este finalizat si nu mai poate fi recalculat.');
    return;
  }
  if (recalculatingCurrentDraft && !window.confirm(
    'Recalculezi targetul acestei luni? Valorile finale si observatiile introduse pana acum vor fi resetate la noul calcul.',
  )) {
    return;
  }
  setBusy(true);
  setError(null);
  try {
    if (dirtyRowsRef.current.size > 0 && !recalculatingCurrentDraft) {
      await persistDraft();
    }
    const calculated = await calculateTargetScenario({
      target_month: targetMonth,
      total_target: parsedTarget,
      min_floor: parsedFloor,
      previous_month_floor_pct: 0,
      previous_month_cap_pct: context?.default_previous_month_cap_pct ?? 1.7,
      seasonality_years: seasonalityYearsFromMode(seasonalityMode),
      expected_revision: recalculatingCurrentDraft
        ? existingTarget.revision
        : undefined,
    });
    replaceScenario(calculated);
    setRegionalFilter('all');
    clearLocalEdits();
  } catch (err) {
    console.error(err);
    setError(getApiErrorMessage(
      err,
      'Calculul nu a putut fi salvat. Verifica parametrii si lunile cu date disponibile.',
    ));
  } finally {
    setBusy(false);
  }
};

const updateRow = (siteCode: string, field: 'final_target' | 'note', value: number | string | null) => {
  const current = scenarioRef.current;
  if (!current || current.status === 'finalized') return;
  const rows = current.rows.map((row) => (
    row.site_code === siteCode ? { ...row, [field]: value } : row
  ));
  replaceScenario(recalculateVisibleScenario(current, rows));
  editVersionsRef.current.set(siteCode, (editVersionsRef.current.get(siteCode) ?? 0) + 1);
  setDirtyRows((previous) => {
    const next = new Set(previous).add(siteCode);
    dirtyRowsRef.current = next;
    return next;
  });
};

const resetToProposal = () => {
  const current = scenarioRef.current;
  if (!current || current.status === 'finalized') return;
  const selectedCodes = new Set(
    current.rows
      .filter((row) => regionalFilter === 'all' || row.regional === regionalFilter)
      .map((row) => row.site_code),
  );
  const rows = current.rows.map((row) => (
    selectedCodes.has(row.site_code)
      ? { ...row, final_target: row.proposed_target, note: null }
      : row
  ));
  replaceScenario(recalculateVisibleScenario(current, rows));
  selectedCodes.forEach((siteCode) => {
    editVersionsRef.current.set(siteCode, (editVersionsRef.current.get(siteCode) ?? 0) + 1);
  });
  setDirtyRows((previous) => {
    const next = new Set(previous);
    selectedCodes.forEach((siteCode) => next.add(siteCode));
    dirtyRowsRef.current = next;
    return next;
  });
};

const persistRows = useCallback(async (siteCodes: string[]): Promise<TargetScenario | null> => {
  const current = scenarioRef.current;
  if (!current || current.status === 'finalized' || siteCodes.length === 0) return current;
  const rowSet = new Set(siteCodes);
  const rowsToSave = current.rows.filter((row) => rowSet.has(row.site_code));
  const submittedVersions = new Map(
    rowsToSave.map((row) => [row.site_code, editVersionsRef.current.get(row.site_code) ?? 0]),
  );
  setSavingRows((previous) => new Set([...previous, ...siteCodes]));
  try {
    const saved = await saveTargetFinalValues(
      current.id,
      {
        expected_revision: current.revision,
        rows: rowsToSave.map((row) => ({
          site_code: row.site_code,
          final_target: row.final_target,
          note: row.note,
        })),
      },
    );
    const remainingDirty = new Set(dirtyRowsRef.current);
    submittedVersions.forEach((version, siteCode) => {
      if ((editVersionsRef.current.get(siteCode) ?? 0) === version) {
        remainingDirty.delete(siteCode);
      }
    });
    dirtyRowsRef.current = remainingDirty;
    setDirtyRows(remainingDirty);

    const latestLocal = scenarioRef.current;
    const localRows = new Map(
      latestLocal?.id === saved.id
        ? latestLocal.rows.map((row) => [row.site_code, row])
        : [],
    );
    const mergedRows = saved.rows.map((row) => (
      remainingDirty.has(row.site_code)
        ? localRows.get(row.site_code) ?? row
        : row
    ));
    replaceScenario(recalculateVisibleScenario(saved, mergedRows));
    setError(null);
    setConflictRetryAvailable(false);
    return saved;
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      setConflictRetryAvailable(true);
    }
    try {
      const latest = await fetchTargetScenario(current.id);
      const latestLocal = scenarioRef.current;
      const localRows = new Map(
        latestLocal?.id === latest.id
          ? latestLocal.rows.map((row) => [row.site_code, row])
          : [],
      );
      const mergedRows = latest.rows.map((row) => (
        dirtyRowsRef.current.has(row.site_code)
          ? localRows.get(row.site_code) ?? row
          : row
      ));
      replaceScenario(recalculateVisibleScenario(latest, mergedRows));
    } catch {
      // Preserve local edits if the conflict refresh is also unavailable.
    }
    throw err;
  } finally {
    setSavingRows((previous) => {
      const next = new Set(previous);
      siteCodes.forEach((siteCode) => next.delete(siteCode));
      return next;
    });
  }
  }, [dirtyRowsRef, editVersionsRef, replaceScenario, scenarioRef, setConflictRetryAvailable, setDirtyRows, setError, setSavingRows]);

const persistDraft = async (): Promise<TargetScenario | null> => {
  const current = scenarioRef.current;
  if (!current || current.status === 'finalized') return current;
  return persistRows(Array.from(dirtyRowsRef.current));
};

const handleSave = async () => {
  setBusy(true);
  setError(null);
  setConflictRetryAvailable(false);
  try {
    await persistDraft();
  } catch (err) {
    console.error(err);
    if (err instanceof ApiError && err.status === 409) {
      setConflictRetryAvailable(true);
    }
    setError(getApiErrorMessage(err, 'Targetele finale nu au putut fi salvate.'));
  } finally {
    setBusy(false);
  }
};

useEffect(() => {
  if (!scenario || scenario.status === 'finalized' || dirtyRows.size === 0) return;
  const pendingCodes = Array.from(dirtyRows).filter((siteCode) => !savingRows.has(siteCode));
  if (pendingCodes.length === 0) return;
  const timeoutId = window.setTimeout(() => {
    void persistRows(pendingCodes).catch((err) => {
      console.error(err);
      setError(getApiErrorMessage(err, 'Salvarea automata a targetelor finale nu a reusit.'));
    });
  }, 700);
  return () => window.clearTimeout(timeoutId);
  }, [scenario, dirtyRows, savingRows, persistRows, setError]);

useEffect(() => {
  if (!scenario || dirtyRows.size > 0 || savingRows.size > 0) return;
  const scenarioId = scenario.id;
  const intervalId = window.setInterval(() => {
    void fetchTargetScenario(scenarioId).then((latest) => {
      if (scenarioRef.current?.id === scenarioId && dirtyRowsRef.current.size === 0) {
        replaceScenario(latest);
      }
    }).catch(() => {
      // Keep the user's current view if a background collaboration refresh fails.
    });
  }, 15000);
  return () => window.clearInterval(intervalId);
  }, [scenario, dirtyRows.size, savingRows.size, dirtyRowsRef, replaceScenario, scenarioRef]);

const handleFinalize = async () => {
  if (!scenario) return;
  setBusy(true);
  setError(null);
  try {
    if (dirty) {
      await persistDraft();
    }
    const latest = await fetchTargetScenario(scenario.id);
    replaceScenario(latest);
    if (latest.pending_final_count > 0) {
      setError(`Mai sunt ${latest.pending_final_count} locatii fara Final manager completat.`);
      return;
    }
    if (Math.abs(latest.remaining_difference) > 0.01) {
      setError('Pentru finalizare, suma targetelor finale trebuie sa fie egala cu targetul total.');
      return;
    }
    if (!window.confirm(
      `Finalizezi scenariul pentru exact cele ${latest.store_count} magazine active? `
      + 'Valorile vor deveni targetele oficiale din Hub si CRM, iar orice target existent in afara acestei cohorte va fi eliminat.',
    )) return;
    replaceScenario(await finalizeTargetScenario(latest.id, {
      expected_revision: latest.revision,
    }));
    clearLocalEdits();
  } catch (err) {
    console.error(err);
    setError(getApiErrorMessage(err, 'Targetul nu a putut fi finalizat.'));
  } finally {
    setBusy(false);
  }
};

const handleExport = async () => {
  if (!scenario) return;
  setBusy(true);
  setError(null);
  try {
    if (dirty && scenario.status === 'draft') {
      await persistDraft();
    }
    await downloadTargetScenario(scenario.id, `targete_${scenario.target_month}.xlsx`);
  } catch (err) {
    console.error(err);
    setError(getApiErrorMessage(err, 'Exportul Excel nu a putut fi generat.'));
  } finally {
    setBusy(false);
  }
};

  return {
    toggleLocationFilter,
    removeLocationFilter,
    handleCalculate,
    updateRow,
    resetToProposal,
    handleSave,
    handleFinalize,
    handleExport,
  };
}
