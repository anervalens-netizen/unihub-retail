import { useState } from 'react';
import { SegmentedTabs } from './common/SegmentedTabs';
import { SalaryHistorySummaryPanel } from '../features/salary/SalaryHistorySummaryPanel';
import { ALL_FIRMS, ALL_SCOPE } from '../lib/filterValues';
import { SalaryArchivePanel } from '../features/salary/SalaryArchivePanel';
import type { AppFilters } from '../lib/appFilters';
import { SalaryAgentsPanel, SalaryAreaPanel, SalaryHeader, SalaryOverviewStats, SalaryTrendPanel, StoreSummaryPanel } from '../features/salary/SalaryViews';
import { useSalaryController } from '../features/salary/useSalaryController';

function OfficialSalaryPanel({ globalFilters }: { globalFilters?: AppFilters }) {
  const model = useSalaryController(globalFilters);
  const julyFilters = { year:2026,month:7,site_code:globalFilters?.magazin,company_name:globalFilters?.firma === ALL_FIRMS ? undefined : globalFilters?.firma,regional:globalFilters?.rm === ALL_SCOPE ? undefined : globalFilters?.rm };
  return <div className="space-y-4 px-4 pb-4 pt-0"><SalaryHeader model={model} />
    <section className="space-y-3 rounded-2xl border border-indigo-100 p-3 dark:border-indigo-900">
      <h3 className="text-sm font-semibold">Iulie 2026 — statele oficiale HR</h3>
      <p className="text-xs text-slate-500">Luna iulie este afișată din cele două state HR, inclusiv pentru numele fără asociere în aplicație. Totalurile de mai jos pentru ianuarie 2025–iunie 2026 rămân separate; nu includ încă iulie.</p>
      <p className="text-xs text-amber-700">Iulie: total recalculat din toate rândurile HR. Formula de total din fișierul Mobiup omite primul angajat; afișarea include și acel rând.</p>
      {model.salaryView === 'agents' ? <SalaryArchivePanel globalFilters={globalFilters} fixedPeriod="2026-07" initialView="agents" hideTabs /> : <SalaryHistorySummaryPanel view={model.salaryView === 'stores' ? 'stores' : 'overview'} filters={julyFilters} />}
    </section>
    <SalaryOverviewStats model={model} /><StoreSummaryPanel model={model} /><SalaryTrendPanel model={model} /><SalaryAreaPanel model={model} /><SalaryAgentsPanel model={model} /></div>;
}

export function SalariiSubtab({ globalFilters }: { globalFilters?: AppFilters }) {
  const [view, setView] = useState<'official' | 'archive'>('official');
  return <div className="space-y-4">
    <h2 className="px-4 text-lg font-semibold">Salarii oficiale</h2>
    <SegmentedTabs ariaLabel="Vizualizare salarii oficiale" options={[{ value: 'official', label: 'Sinteză existentă' }, { value: 'archive', label: 'Istoric' }]} value={view} onChange={setView} className="mx-auto max-w-lg" />
    {view === 'archive' ? <SalaryArchivePanel globalFilters={globalFilters} /> : <OfficialSalaryPanel globalFilters={globalFilters} />}
  </div>;
}
