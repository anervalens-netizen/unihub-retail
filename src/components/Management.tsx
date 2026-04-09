import { useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { CRMSubtab } from './CRMSubtab';
import { TasksSubtab } from './TasksSubtab';
import { HRSubtab } from './HRSubtab';

type ManagementTab = 'asm' | 'crm' | 'tasks' | 'hr';

const TABS: { id: ManagementTab; label: string }[] = [
  { id: 'asm', label: 'Echipă' },
  { id: 'crm', label: 'Magazine' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'hr', label: 'HR' },
];

export function Management() {
  const [activeTab, setActiveTab] = useState<ManagementTab>('asm');

  return (
    <div className="flex flex-col h-full">
      {/* Sub-navigare */}
      <div className="flex gap-1 px-4 pt-4 pb-2 border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'text-white/60 hover:text-white hover:bg-white/10'
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
        {activeTab === 'tasks' && <TasksSubtab />}
        {activeTab === 'hr' && <HRSubtab />}
      </div>
    </div>
  );
}
