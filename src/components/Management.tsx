import { lazy, Suspense, useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { TargetCalculatorSubtab } from '../features/target-calculator/TargetCalculatorPage';
import { SalariiSubtab } from './SalariiSubtab';
import { PnlSubtab } from './PnlSubtab';
import type { ManagementTab } from '../lib/tabs';
import type { AppFilters } from '../lib/appFilters';
import { SegmentedTabs, type SegmentedTabOption } from './common/SegmentedTabs';
import { PageHeader } from './common/DesktopLayout';
import { cn } from '../lib/utils';
function LoadingFieldOps() { return <div className="flex min-h-32 items-center justify-center text-sm font-semibold text-slate-500">Se incarca FieldOps...</div>; }

const VisiteSubtab = lazy(async () => ({ default: (await import('./VisiteSubtab')).VisiteSubtab }));
const TABS: SegmentedTabOption<ManagementTab>[] = [
  { value: 'asm', label: 'Manageri' },
  { value: 'target-calculator', label: 'Calculator Target' },
  { value: 'salarii', label: 'Salarii' },
  { value: 'fieldops', label: 'FieldOps' },
  { value: 'pnl', label: 'P&L' },
];

interface Props {
  activeSubTab?: ManagementTab;
  setActiveSubTab?: (tab: ManagementTab) => void;
  hasPnlAccess?: boolean;
  currentMonth?: string;
  months?: string[];
  salaryFilters: AppFilters;
}

export function Management({ activeSubTab, setActiveSubTab, hasPnlAccess = false, currentMonth, months = [], salaryFilters }: Props) {
  const [localTab, setLocalTab] = useState<ManagementTab>('asm');

  const activeTab = activeSubTab ?? localTab;
  const setTab = (tab: ManagementTab) => {
    setLocalTab(tab);
    setActiveSubTab?.(tab);
  };

  return (
    <div className="flex h-full flex-col lg:px-6 lg:py-3">
      <div className="space-y-3 p-3 pb-0 pt-2 lg:hidden">
        <PageHeader
          title="Management"
          description="Echipa, targete, salarii si analiza financiara"
        />
      </div>

      <SegmentedTabs
        ariaLabel="Secțiuni Management"
        className="glass mx-3 mt-3 lg:mx-0 lg:mt-0"
        options={TABS.filter((tab) => tab.value !== 'pnl' || hasPnlAccess)}
        value={activeTab}
        onChange={setTab}
      />

      <div className={cn('flex-1', activeTab === 'salarii' ? 'mt-0' : 'mt-3 lg:mt-4')}>
        {activeTab === 'asm' && <ASMSubtab currentMonth={currentMonth} />}
        {activeTab === 'target-calculator' && <TargetCalculatorSubtab />}
        {activeTab === 'salarii' && <SalariiSubtab globalFilters={salaryFilters} />}
        {activeTab === 'fieldops' && currentMonth && <Suspense fallback={<LoadingFieldOps />}><VisiteSubtab currentMonth={currentMonth} months={months} /></Suspense>}
        {activeTab === 'pnl' && hasPnlAccess && <PnlSubtab />}
      </div>
    </div>
  );
}
