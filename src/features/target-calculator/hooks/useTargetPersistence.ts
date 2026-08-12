import { useCallback, useEffect } from 'react';

import { ApiError, getApiErrorMessage } from '../../../api/client';
import { fetchTargetScenario, saveTargetFinalValues, type TargetScenario } from '../api';
import { recalculateVisibleScenario } from '../model';
import type { PersistDraft, TargetScenarioActionDeps } from './targetScenarioActionTypes';

export function usePersistTargetRows(deps: TargetScenarioActionDeps) {
  const {
    scenarioRef, dirtyRowsRef, editVersionsRef, replaceScenario,
    setConflictRetryAvailable, setDirtyRows, setError, setSavingRows,
  } = deps;
  const persistRows = useCallback(async (siteCodes: string[]): Promise<TargetScenario | null> => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized' || siteCodes.length === 0) return current;
    const rowSet = new Set(siteCodes);
    const rowsToSave = current.rows.filter((row) => rowSet.has(row.site_code));
    const submittedVersions = new Map(rowsToSave.map((row) => [row.site_code, editVersionsRef.current.get(row.site_code) ?? 0]));
    setSavingRows((previous) => new Set([...previous, ...siteCodes]));
    try {
      const saved = await saveTargetFinalValues(current.id, {
        expected_revision: current.revision,
        rows: rowsToSave.map((row) => ({ site_code: row.site_code, final_target: row.final_target, note: row.note })),
      });
      const remainingDirty = new Set(dirtyRowsRef.current);
      submittedVersions.forEach((version, siteCode) => {
        if ((editVersionsRef.current.get(siteCode) ?? 0) === version) remainingDirty.delete(siteCode);
      });
      dirtyRowsRef.current = remainingDirty;
      setDirtyRows(remainingDirty);
      const latestLocal = scenarioRef.current;
      const localRows = new Map(latestLocal?.id === saved.id ? latestLocal.rows.map((row) => [row.site_code, row]) : []);
      const mergedRows = saved.rows.map((row) => remainingDirty.has(row.site_code) ? localRows.get(row.site_code) ?? row : row);
      replaceScenario(recalculateVisibleScenario(saved, mergedRows));
      setError(null); setConflictRetryAvailable(false);
      return saved;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setConflictRetryAvailable(true);
      try {
        const latest = await fetchTargetScenario(current.id);
        const latestLocal = scenarioRef.current;
        const localRows = new Map(latestLocal?.id === latest.id ? latestLocal.rows.map((row) => [row.site_code, row]) : []);
        const mergedRows = latest.rows.map((row) => dirtyRowsRef.current.has(row.site_code) ? localRows.get(row.site_code) ?? row : row);
        replaceScenario(recalculateVisibleScenario(latest, mergedRows));
      } catch {
        // Preserve local edits if the conflict refresh is also unavailable.
      }
      throw error;
    } finally {
      setSavingRows((previous) => {
        const next = new Set(previous);
        siteCodes.forEach((siteCode) => next.delete(siteCode));
        return next;
      });
    }
  }, [dirtyRowsRef, editVersionsRef, replaceScenario, scenarioRef, setConflictRetryAvailable, setDirtyRows, setError, setSavingRows]);
  const persistDraft: PersistDraft = async () => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return current;
    return persistRows(Array.from(dirtyRowsRef.current));
  };
  return { persistRows, persistDraft };
}

export function useTargetPersistenceEffects(
  deps: TargetScenarioActionDeps,
  persistRows: (siteCodes: string[]) => Promise<TargetScenario | null>,
) {
  const { scenario, dirtyRows, savingRows, scenarioRef, dirtyRowsRef, replaceScenario, setError } = deps;
  useEffect(() => {
    if (!scenario || scenario.status === 'finalized' || dirtyRows.size === 0) return;
    const pendingCodes = Array.from(dirtyRows).filter((siteCode) => !savingRows.has(siteCode));
    if (pendingCodes.length === 0) return;
    const timeoutId = window.setTimeout(() => {
      void persistRows(pendingCodes).catch((error) => {
        console.error(error);
        setError(getApiErrorMessage(error, 'Salvarea automata a targetelor finale nu a reusit.'));
      });
    }, 700);
    return () => window.clearTimeout(timeoutId);
  }, [dirtyRows, persistRows, savingRows, scenario, setError]);
  useEffect(() => {
    if (!scenario || dirtyRows.size > 0 || savingRows.size > 0) return;
    const scenarioId = scenario.id;
    const intervalId = window.setInterval(() => {
      void fetchTargetScenario(scenarioId).then((latest) => {
        if (scenarioRef.current?.id === scenarioId && dirtyRowsRef.current.size === 0) replaceScenario(latest);
      }).catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [dirtyRows.size, dirtyRowsRef, replaceScenario, savingRows.size, scenario, scenarioRef]);
}

export function useTargetSaveAction(deps: TargetScenarioActionDeps, persistDraft: PersistDraft) {
  const { setBusy, setConflictRetryAvailable, setError } = deps;
  const handleSave = async () => {
    setBusy(true); setError(null); setConflictRetryAvailable(false);
    try { await persistDraft(); }
    catch (error) {
      console.error(error);
      if (error instanceof ApiError && error.status === 409) setConflictRetryAvailable(true);
      setError(getApiErrorMessage(error, 'Targetele finale nu au putut fi salvate.'));
    } finally { setBusy(false); }
  };
  return handleSave;
}

