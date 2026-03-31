export type Role = 'admin' | 'asm' | 'management' | 'tl';
export type TabId = 'hub' | 'focus' | 'agents' | 'ai' | 'settings';
export type SubTabId = 'vizite' | 'salarii';

export const ROLE_HIERARCHY: Role[] = ['tl', 'asm', 'management', 'admin'];

export const ROLE_TABS: Record<Role, TabId[]> = {
  tl: ['hub', 'focus', 'agents', 'ai', 'settings'],
  asm: ['hub', 'focus', 'agents', 'ai', 'settings'],
  management: ['hub', 'focus', 'agents', 'ai', 'settings'],
  admin: ['hub', 'focus', 'agents', 'ai', 'settings'],
};

export const ROLE_SUBTABS: Record<SubTabId, Role[]> = {
  vizite: ['management', 'admin'],
  salarii: ['admin'],
};

export const TAB_LABELS: Record<TabId, string> = {
  hub: 'Hub',
  focus: 'Focus',
  agents: 'Agenti',
  ai: 'AI',
  settings: 'Setări',
};

export function canAccessTab(role: Role, tab: TabId): boolean {
  return ROLE_TABS[role]?.includes(tab) ?? false;
}

export function getRoleAccessLabel(role: Role): string {
  const tabs = ROLE_TABS[role];
  const label = tabs.map((t) => TAB_LABELS[t]).join(' · ');
  if (role === 'tl' || role === 'asm' || role === 'management') {
    return label + ' · Setari (doar temă)';
  }
  return label;
}
