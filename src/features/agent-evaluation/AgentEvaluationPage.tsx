import {
  EvaluationContent,
  EvaluationHeader,
  EvaluationMobileFilters,
} from './AgentEvaluationViews';
import { useAgentEvaluationController } from './useAgentEvaluationController';

export function AgentEvaluationSubtab({ currentMonth, months }: {
  currentMonth: string;
  months: string[];
}) {
  const model = useAgentEvaluationController(currentMonth, months);
  return <div className="space-y-3 p-3 md:p-4">
    <EvaluationHeader model={model} />
    <EvaluationMobileFilters model={model} />
    <EvaluationContent model={model} />
  </div>;
}
