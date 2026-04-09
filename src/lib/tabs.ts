import { Bot, Briefcase, CheckSquare, LayoutDashboard, Settings, Sparkles, UserCog, Users, Building2 } from 'lucide-react';
import type { TabId } from './roles';

export type ManagementTab = 'asm' | 'crm' | 'tasks' | 'hr';

export const ALL_TABS = [
  { id: 'hub', icon: LayoutDashboard, label: 'Hub' },
  { id: 'focus', icon: Sparkles, label: 'Focus' },
  { id: 'agents', icon: Users, label: 'Agenti' },
  { id: 'management', icon: Briefcase, label: 'Management' },
  { id: 'ai', icon: Bot, label: 'AI' },
  { id: 'settings', icon: Settings, label: 'Setari' },
] as const;

export const MGMT_SUBTABS = [
  { id: 'asm' as ManagementTab, label: 'Echipă', icon: Users },
  { id: 'crm' as ManagementTab, label: 'Magazine', icon: Building2 },
  { id: 'tasks' as ManagementTab, label: 'Tasks', icon: CheckSquare },
  { id: 'hr' as ManagementTab, label: 'HR', icon: UserCog },
];

export const TAB_LABELS: Record<TabId, string> = {
  hub: 'Sales Hub',
  focus: 'Focus & Campanii',
  agents: 'Agenți',
  management: 'Management',
  ai: 'AI Assistant',
  settings: 'Setări',
};

export const MGMT_SUBTAB_LABELS: Record<ManagementTab, string> = {
  asm: 'Echipă',
  crm: 'Magazine',
  tasks: 'Tasks',
  hr: 'HR',
};
