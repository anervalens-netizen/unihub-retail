import { BadgeDollarSign, Briefcase, Calculator, LayoutDashboard, Settings, Sparkles, Users } from 'lucide-react';

export type TabId = 'hub' | 'focus' | 'agents' | 'management' | 'settings';
export type ManagementTab = 'asm' | 'target-calculator' | 'salarii' | 'pnl';

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
  { id: 'salarii' as ManagementTab, label: 'Salarii', icon: BadgeDollarSign },
  { id: 'pnl' as ManagementTab, label: 'P&L', icon: BadgeDollarSign, ownerOnly: true },
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
  salarii: 'Salarii',
  pnl: 'P&L',
};
