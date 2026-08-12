import { getApiErrorMessage } from '../../../api/client';
import { seasonalityYearsFromMode } from '../../../lib/targetSeasonality';
import {
  calculateTargetScenario,
  downloadTargetScenario,
  fetchTargetScenario,
  finalizeTargetScenario,
} from '../api';
import { recalculateVisibleScenario } from '../model';
import type { PersistDraft, TargetScenarioActionDeps } from './targetScenarioActionTypes';

export function useTargetLocationActions(deps: TargetScenarioActionDeps) {
  const { setSelectedLocationCodes } = deps;
  return {
    toggleLocationFilter: (siteCode: string) => {
      if (!siteCode) return;
      setSelectedLocationCodes((current) => current.includes(siteCode) ? current.filter((item) => item !== siteCode) : [...current, siteCode]);
    },
    removeLocationFilter: (siteCode: string) => {
      setSelectedLocationCodes((current) => current.filter((item) => item !== siteCode));
    },
  };
}

export function useTargetEditingActions(deps: TargetScenarioActionDeps) {
  const { scenarioRef, regionalFilter, replaceScenario, editVersionsRef, dirtyRowsRef, setDirtyRows } = deps;
  const markDirty = (siteCodes: Set<string>) => {
    siteCodes.forEach((siteCode) => editVersionsRef.current.set(siteCode, (editVersionsRef.current.get(siteCode) ?? 0) + 1));
    setDirtyRows((previous) => {
      const next = new Set(previous); siteCodes.forEach((siteCode) => next.add(siteCode));
      dirtyRowsRef.current = next; return next;
    });
  };
  const updateRow = (siteCode: string, field: 'final_target' | 'note', value: number | string | null) => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return;
    const rows = current.rows.map((row) => row.site_code === siteCode ? { ...row, [field]: value } : row);
    replaceScenario(recalculateVisibleScenario(current, rows));
    markDirty(new Set([siteCode]));
  };
  const resetToProposal = () => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return;
    const selectedCodes = new Set(current.rows.filter((row) => regionalFilter === 'all' || row.regional === regionalFilter).map((row) => row.site_code));
    const rows = current.rows.map((row) => selectedCodes.has(row.site_code) ? { ...row, final_target: row.proposed_target, note: null } : row);
    replaceScenario(recalculateVisibleScenario(current, rows));
    markDirty(selectedCodes);
  };
  return { updateRow, resetToProposal };
}

export function useTargetCalculateAction(deps: TargetScenarioActionDeps, persistDraft: PersistDraft) {
  const {
    context, targetMonth, totalTarget, minFloor, seasonalityMode, scenarioRef,
    dirtyRowsRef, replaceScenario, setRegionalFilter, clearLocalEdits, setBusy, setError,
  } = deps;
  return async () => {
    const parsedTarget = Number(totalTarget); const parsedFloor = Number(minFloor);
    if (seasonalityMode === null) { setError('Asteapta initializarea modului de sezonalitate.'); return; }
    if (!targetMonth || parsedTarget <= 0 || parsedFloor < 0) { setError('Completeaza parametrii de calcul cu valori valide.'); return; }
    const existingTarget = scenarioRef.current;
    const recalculating = existingTarget?.target_month === targetMonth && existingTarget.status === 'draft';
    if (existingTarget?.target_month === targetMonth && existingTarget.status === 'finalized') {
      setError('Targetul acestei luni este finalizat si nu mai poate fi recalculat.'); return;
    }
    if (recalculating && !window.confirm('Recalculezi targetul acestei luni? Valorile finale si observatiile introduse pana acum vor fi resetate la noul calcul.')) return;
    setBusy(true); setError(null);
    try {
      if (dirtyRowsRef.current.size > 0 && !recalculating) await persistDraft();
      const calculated = await calculateTargetScenario({
        target_month: targetMonth, total_target: parsedTarget, min_floor: parsedFloor,
        previous_month_floor_pct: 0,
        previous_month_cap_pct: context?.default_previous_month_cap_pct ?? 1.7,
        seasonality_years: seasonalityYearsFromMode(seasonalityMode),
        expected_revision: recalculating ? existingTarget.revision : undefined,
      });
      replaceScenario(calculated); setRegionalFilter('all'); clearLocalEdits();
    } catch (error) {
      console.error(error);
      setError(getApiErrorMessage(error, 'Calculul nu a putut fi salvat. Verifica parametrii si lunile cu date disponibile.'));
    } finally { setBusy(false); }
  };
}

export function useTargetFinalActions(deps: TargetScenarioActionDeps, persistDraft: PersistDraft) {
  const { scenario, dirty, replaceScenario, clearLocalEdits, setBusy, setError } = deps;
  const handleFinalize = async () => {
    if (!scenario) return;
    setBusy(true); setError(null);
    try {
      if (dirty) await persistDraft();
      const latest = await fetchTargetScenario(scenario.id); replaceScenario(latest);
      if (latest.pending_final_count > 0) { setError(`Mai sunt ${latest.pending_final_count} locatii fara Final manager completat.`); return; }
      if (Math.abs(latest.remaining_difference) > 0.01) { setError('Pentru finalizare, suma targetelor finale trebuie sa fie egala cu targetul total.'); return; }
      if (!window.confirm(`Finalizezi scenariul pentru exact cele ${latest.store_count} magazine active? ` + 'Valorile vor deveni targetele oficiale din Hub si CRM, iar orice target existent in afara acestei cohorte va fi eliminat.')) return;
      replaceScenario(await finalizeTargetScenario(latest.id, { expected_revision: latest.revision }));
      clearLocalEdits();
    } catch (error) {
      console.error(error); setError(getApiErrorMessage(error, 'Targetul nu a putut fi finalizat.'));
    } finally { setBusy(false); }
  };
  const handleExport = async () => {
    if (!scenario) return;
    setBusy(true); setError(null);
    try {
      if (dirty && scenario.status === 'draft') await persistDraft();
      await downloadTargetScenario(scenario.id, `targete_${scenario.target_month}.xlsx`);
    } catch (error) {
      console.error(error); setError(getApiErrorMessage(error, 'Exportul Excel nu a putut fi generat.'));
    } finally { setBusy(false); }
  };
  return { handleFinalize, handleExport };
}

