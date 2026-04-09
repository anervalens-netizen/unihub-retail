import { useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { CRMSubtab } from './CRMSubtab';
import { TasksSubtab } from './TasksSubtab';
import { HRSubtab } from './HRSubtab';
import type { ManagementTab } from '../lib/tabs';

const TABS: { id: ManagementTab; label: string }[] = [
  { id: 'asm', label: 'Echipă' },
  { id: 'crm', label: 'Magazine' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'hr', label: 'HR' },
];

interface Props {
  userRole?: string;
  userFullName?: string;
  activeSubTab?: ManagementTab;
  setActiveSubTab?: (tab: ManagementTab) => void;
}

export function Management({ userRole, userFullName, activeSubTab, setActiveSubTab }: Props) {
  const [localTab, setLocalTab] = useState<ManagementTab>('asm');

  const activeTab = activeSubTab ?? localTab;
  const setTab = (tab: ManagementTab) => {
    setLocalTab(tab);
    setActiveSubTab?.(tab);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Sub-navigare — vizibilă doar pe mobile (pe desktop controlată din sidebar) */}
      <div className="lg:hidden flex gap-1 px-4 pt-4 pb-2 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setTab(tab.id)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Conținut */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'asm' && <ASMSubtab />}
        {activeTab === 'crm' && <CRMSubtab />}
        {activeTab === 'tasks' && <TasksSubtab userRole={userRole} userFullName={userFullName} />}
        {activeTab === 'hr' && <HRSubtab />}
      </div>
    </div>
  );
}
