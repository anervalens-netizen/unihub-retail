import type { TargetScenarioActionDeps } from './targetScenarioActionTypes';
import {
  useTargetCalculateAction,
  useTargetEditingActions,
  useTargetFinalActions,
  useTargetLocationActions,
} from './useTargetActionGroups';
import {
  usePersistTargetRows,
  useTargetPersistenceEffects,
  useTargetSaveAction,
} from './useTargetPersistence';

export function useTargetScenarioActions(deps: TargetScenarioActionDeps) {
  const { persistRows, persistDraft } = usePersistTargetRows(deps);
  useTargetPersistenceEffects(deps, persistRows);
  const location = useTargetLocationActions(deps);
  const editing = useTargetEditingActions(deps);
  const handleCalculate = useTargetCalculateAction(deps, persistDraft);
  const handleSave = useTargetSaveAction(deps, persistDraft);
  const finalActions = useTargetFinalActions(deps, persistDraft);
  return {
    ...location,
    ...editing,
    handleCalculate,
    handleSave,
    ...finalActions,
  };
}
