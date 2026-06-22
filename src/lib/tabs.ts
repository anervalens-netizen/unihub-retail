import { Briefcase, Calculator, ClipboardCheck, LayoutDashboard, Settings, Sparkles, Users } from 'lucide-react';

export type TabId = 'hub' | 'focus' | 'agents' | 'management' | 'settings';
export type ManagementTab = 'asm' | 'target-calculator' | 'grile';

export const ALL_TABS = [
  { id: 'hub', icon: LayoutDashboard, label: 'Hub' },
  { id: 'focus', icon: Sparkles, label: 'Focus' },
  { id: 'agents', icon: Users, label: 'Agenti' },
  { id: 'management', icon: Briefcase, label: 'Management' },
  { id: 'settings', icon: Settings, label: 'Setari' },
] as const;

export const MGMT_SUBTABS = [
  { id: 'asm' as ManagementTab, label: 'Manageri', icon: Users },
  { id: 'target-calculator' as ManagementTab, label: 'Calculator Target', icon: Calculator },
  { id: 'grile' as ManagementTab, label: 'Grile', icon: ClipboardCheck },
];

export const TAB_LABELS: Record<TabId, string> = {
  hub: 'Sales Hub',
  focus: 'Focus & Campanii',
  agents: 'Agenți',
  management: 'Management',
  settings: 'Setări',
};

export const MGMT_SUBTAB_LABELS: Record<ManagementTab, string> = {
  asm: 'Manageri',
  'target-calculator': 'Calculator Target',
  grile: 'Grile',
};
