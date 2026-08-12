import type { AppFilters } from '../lib/appFilters';
import { SalaryAgentsPanel, SalaryAreaPanel, SalaryHeader, SalaryOverviewStats, SalaryTrendPanel, StoreSummaryPanel } from '../features/salary/SalaryViews';
import { useSalaryController } from '../features/salary/useSalaryController';

export function SalariiSubtab({ globalFilters }: { globalFilters?: AppFilters }) {
  const model = useSalaryController(globalFilters);
  return <div className="space-y-4 px-4 pb-4 pt-0"><SalaryHeader model={model} /><SalaryOverviewStats model={model} /><StoreSummaryPanel model={model} /><SalaryTrendPanel model={model} /><SalaryAreaPanel model={model} /><SalaryAgentsPanel model={model} /></div>;
}
