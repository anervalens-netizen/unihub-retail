import { Briefcase, Calculator, ClipboardCheck, LayoutDashboard, Settings, Sparkles, Users, Building2 } from 'lucide-react';

export type TabId = 'hub' | 'focus' | 'agents' | 'management' | 'settings';
export type ManagementTab = 'asm' | 'crm' | 'target-calculator' | 'grile';

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
  asm: 'Echipă',
  crm: 'Magazine',
  'target-calculator': 'Calculator Target',
  grile: 'Grile',
};
