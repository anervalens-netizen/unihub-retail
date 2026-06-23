import type { TabId } from './tabs';

const TAB_IDS = new Set<TabId>([
  'hub',
  'focus',
  'agents',
  'management',
  'settings',
]);

export function sanitizeActiveTab(
  value: string | null | undefined,
  canAccessManagement: boolean,
): TabId {
  const tab = value && TAB_IDS.has(value as TabId) ? (value as TabId) : 'hub';
  if (tab === 'management' && !canAccessManagement) return 'hub';
  return tab;
}
