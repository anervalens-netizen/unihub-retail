import { TargetScenarioView } from './TargetScenarioView';
import { useTargetScenario } from './hooks/useTargetScenario';

export function TargetCalculatorPage() {
  const model = useTargetScenario();

  if (model.loading) {
    return <div className="p-6 text-sm text-slate-500">Se incarca calculatorul de target...</div>;
  }

  return <TargetScenarioView {...model} />;
}

/** Stable public name used by Management while callers migrate to the feature page. */
export { TargetCalculatorPage as TargetCalculatorSubtab };
export { TargetErrorNotice } from './TargetScenarioView';
