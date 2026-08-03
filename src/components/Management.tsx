import { useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { TargetCalculatorSubtab } from './TargetCalculatorSubtab';
import { SalariiSubtab } from './SalariiSubtab';
import { PnlSubtab } from './PnlSubtab';
import type { ManagementTab } from '../lib/tabs';
import type { AppFilters } from './MainLayout';
import { SegmentedTabs, type SegmentedTabOption } from './common/SegmentedTabs';
import { PageHeader } from './common/DesktopLayout';

const TABS: SegmentedTabOption<ManagementTab>[] = [
  { value: 'asm', label: 'Manageri' },
  { value: 'target-calculator', label: 'Calculator Target' },
  { value: 'salarii', label: 'Salarii' },
  { value: 'pnl', label: 'P&L' },
];

interface Props {
  activeSubTab?: ManagementTab;
  setActiveSubTab?: (tab: ManagementTab) => void;
  hasPnlAccess?: boolean;
  currentMonth?: string;
  salaryFilters: AppFilters;
}

export function Management({ activeSubTab, setActiveSubTab, hasPnlAccess = false, currentMonth, salaryFilters }: Props) {
  const [localTab, setLocalTab] = useState<ManagementTab>('asm');

  const activeTab = activeSubTab ?? localTab;
  const setTab = (tab: ManagementTab) => {
    setLocalTab(tab);
    setActiveSubTab?.(tab);
  };

  return (
    <div className="flex h-full flex-col lg:px-6 lg:py-3">
      <div className="space-y-3 p-3 pb-0 pt-2 lg:space-y-4 lg:p-0">
        <PageHeader
          title="Management"
          description="Echipa, targete, salarii si analiza financiara"
        />
      </div>

      <SegmentedTabs
        ariaLabel="Secțiuni Management"
        className="glass mx-3 mt-3 lg:mx-0"
        options={TABS.filter((tab) => tab.value !== 'pnl' || hasPnlAccess)}
        value={activeTab}
        onChange={setTab}
      />

      <div className="mt-3 flex-1 lg:mt-4">
        {activeTab === 'asm' && <ASMSubtab currentMonth={currentMonth} />}
        {activeTab === 'target-calculator' && <TargetCalculatorSubtab />}
        {activeTab === 'salarii' && <SalariiSubtab globalFilters={salaryFilters} />}
        {activeTab === 'pnl' && hasPnlAccess && <PnlSubtab />}
      </div>
    </div>
  );
}
