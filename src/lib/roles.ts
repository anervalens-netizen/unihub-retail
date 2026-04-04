export type Role = 'admin' | 'asm' | 'management' | 'tl';
export type TabId = 'hub' | 'focus' | 'agents' | 'ai' | 'settings';

const ROLE_TABS: Record<Role, TabId[]> = {
  tl: ['hub', 'focus', 'agents', 'ai', 'settings'],
  asm: ['hub', 'focus', 'agents', 'ai', 'settings'],
  management: ['hub', 'focus', 'agents', 'ai', 'settings'],
  admin: ['hub', 'focus', 'agents', 'ai', 'settings'],
};

const TAB_LABELS: Record<TabId, string> = {
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
  if (role === 'tl' || role === 'asm' || role === 'management') {
    const label = tabs.filter((t) => t !== 'settings').map((t) => TAB_LABELS[t]).join(' · ');
    return label + ' · Setări (doar temă)';
  }
  return tabs.map((t) => TAB_LABELS[t]).join(' · ');
}
