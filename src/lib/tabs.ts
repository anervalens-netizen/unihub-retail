import { Briefcase, Calculator, CheckSquare, LayoutDashboard, Settings, Sparkles, UserCog, Users, Building2 } from 'lucide-react';

export type TabId = 'hub' | 'focus' | 'agents' | 'management' | 'settings';
export type ManagementTab = 'asm' | 'crm' | 'tasks' | 'hr' | 'target-calculator';

export const ALL_TABS = [
  { id: 'hub', icon: LayoutDashboard, label: 'Hub' },
  { id: 'focus', icon: Sparkles, label: 'Focus' },
  { id: 'agents', icon: Users, label: 'Agenti' },
  { id: 'management', icon: Briefcase, label: 'Management' },
  { id: 'settings', icon: Settings, label: 'Setari' },
] as const;

export const MGMT_SUBTABS = [
  { id: 'asm' as ManagementTab, label: 'Echipă', icon: Users },
  { id: 'crm' as ManagementTab, label: 'Magazine', icon: Building2 },
  { id: 'tasks' as ManagementTab, label: 'Tasks', icon: CheckSquare },
  { id: 'hr' as ManagementTab, label: 'HR', icon: UserCog },
  { id: 'target-calculator' as ManagementTab, label: 'Calculator Target', icon: Calculator },
];

export const TAB_LABELS: Record<TabId, string> = {
  hub: 'Sales Hub',
  focus: 'Focus & Campanii',
  agents: 'Agenți',
  management: 'Management',
  settings: 'Setări',
};

export const MGMT_SUBTAB_LABELS: Record<ManagementTab, string> = {
  asm: 'Echipă',
  crm: 'Magazine',
  tasks: 'Tasks',
  hr: 'HR',
  'target-calculator': 'Calculator Target',
};
