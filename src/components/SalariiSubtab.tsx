import { useState } from 'react';
import { SegmentedTabs } from './common/SegmentedTabs';
import { SalaryArchivePanel } from '../features/salary/SalaryArchivePanel';
import type { AppFilters } from '../lib/appFilters';
import { SalaryAgentsPanel, SalaryAreaPanel, SalaryHeader, SalaryOverviewStats, SalaryTrendPanel, StoreSummaryPanel } from '../features/salary/SalaryViews';
import { useSalaryController } from '../features/salary/useSalaryController';

function OfficialSalaryPanel({ globalFilters }: { globalFilters?: AppFilters }) {
  const model = useSalaryController(globalFilters);
  return <div className="space-y-4 px-4 pb-4 pt-0"><SalaryHeader model={model} /><SalaryOverviewStats model={model} /><StoreSummaryPanel model={model} /><SalaryTrendPanel model={model} /><SalaryAreaPanel model={model} /><SalaryAgentsPanel model={model} /></div>;
}

export function SalariiSubtab({ globalFilters }: { globalFilters?: AppFilters }) {
  const [view, setView] = useState<'official' | 'archive'>('archive');
  return <div className="space-y-4">
    <h2 className="px-4 text-lg font-semibold">Salarii oficiale</h2>
    <SegmentedTabs ariaLabel="Vizualizare salarii oficiale" options={[{ value: 'archive', label: 'Istoric state HR' }, { value: 'official', label: 'Sinteză existentă' }]} value={view} onChange={setView} className="mx-auto max-w-lg" />
    {view === 'archive' ? <SalaryArchivePanel globalFilters={globalFilters} /> : <OfficialSalaryPanel globalFilters={globalFilters} />}
  </div>;
}
