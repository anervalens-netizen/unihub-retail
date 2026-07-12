import { useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { TargetCalculatorSubtab } from './TargetCalculatorSubtab';
import { SalariiSubtab } from './SalariiSubtab';
import { PnlSubtab } from './PnlSubtab';
import type { ManagementTab } from '../lib/tabs';
import type { AppFilters } from './MainLayout';

const TABS: { id: ManagementTab; label: string }[] = [
  { id: 'asm', label: 'Manageri' },
  { id: 'target-calculator', label: 'Calculator Target' },
  { id: 'salarii', label: 'Salarii' },
  { id: 'pnl', label: 'P&L' },
];

interface Props {
  activeSubTab?: ManagementTab;
  setActiveSubTab?: (tab: ManagementTab) => void;
  hasPnlAccess?: boolean;
  salaryFilters: AppFilters;
}

export function Management({ activeSubTab, setActiveSubTab, hasPnlAccess = false, salaryFilters }: Props) {
  const [localTab, setLocalTab] = useState<ManagementTab>('asm');

  const activeTab = activeSubTab ?? localTab;
  const setTab = (tab: ManagementTab) => {
    setLocalTab(tab);
    setActiveSubTab?.(tab);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="space-y-3 p-3 pb-0 pt-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Management</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Echipa, targete, salarii si analiza financiara
          </p>
        </div>
      </div>

      <div className="mx-3 mt-3 flex gap-1 overflow-x-auto rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
        {TABS.filter((tab) => tab.id !== 'pnl' || hasPnlAccess).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setTab(tab.id)}
            className={`min-w-fit flex-1 rounded-xl px-4 py-2 text-sm font-bold transition-all ${
              activeTab === tab.id
                ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="mt-3 flex-1 overflow-y-auto">
        {activeTab === 'asm' && <ASMSubtab />}
        {activeTab === 'target-calculator' && <TargetCalculatorSubtab />}
        {activeTab === 'salarii' && <SalariiSubtab globalFilters={salaryFilters} />}
        {activeTab === 'pnl' && hasPnlAccess && <PnlSubtab />}
      </div>
    </div>
  );
}
