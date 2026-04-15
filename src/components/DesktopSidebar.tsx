import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown, LogOut } from 'lucide-react';
import type { AuthUser } from '../api/types';
import { canAccessTab, isManagerRole, type Role, type TabId } from '../lib/roles';
import { ALL_TABS, MGMT_SUBTABS, type ManagementTab } from '../lib/tabs';
import { ThemeSwitcher } from './ThemeSwitcher';
import { cn } from '../lib/utils';

interface Props {
  user: AuthUser | null;
  activeTab: string;
  setActiveTab: (tab: TabId) => void;
  mgmtSubTab: ManagementTab;
  setMgmtSubTab: (tab: ManagementTab) => void;
  theme: string;
  setTheme: (theme: string) => void;
  onLogout: () => void;
  pendingTaskCount: number;
  userRole: Role;
  errorCount?: number;
}

export function DesktopSidebar({
  user,
  activeTab,
  setActiveTab,
  mgmtSubTab,
  setMgmtSubTab,
  theme,
  setTheme,
  onLogout,
  pendingTaskCount,
  userRole,
  errorCount = 0,
}: Props) {
  const [mgmtExpanded, setMgmtExpanded] = useState(activeTab === 'management');

  useEffect(() => {
    if (activeTab === 'management') {
      setMgmtExpanded(true);
    } else {
      setMgmtExpanded(false);
    }
  }, [activeTab]);

  const visibleTabs = ALL_TABS.filter((tab) => canAccessTab(userRole, tab.id as TabId));
  const initials = ((user?.full_name?.trim() || user?.username || '?'))
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const roleLabel: Record<Role, string> = {
    admin: 'Admin',
    management: 'Regional',
    asm: 'ASM',
    tl: 'Team Lead',
  };

  return (
    <aside className="hidden lg:flex flex-col h-full w-60 shrink-0 border-r border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl z-40">
      {/* Header */}
      <div className="flex items-center gap-2.5 h-14 px-4 border-b border-[var(--glass-border)] shrink-0">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white text-xs font-bold shrink-0">
          U
        </div>
        <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100">
          UniHub
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          const showBadge =
            pendingTaskCount > 0 &&
            ((isManagerRole(userRole) && tab.id === 'management') ||
              (!isManagerRole(userRole) && tab.id === 'hub'));
          const isMgmt = tab.id === 'management';

          return (
            <div key={tab.id}>
              <button
                onClick={() => {
                  setActiveTab(tab.id as TabId);
                  if (isMgmt) setMgmtExpanded((p) => !p);
                }}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 text-left',
                  isActive
                    ? 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border-l-2 border-indigo-500 rounded-l-none pl-[10px]'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100/80 dark:hover:bg-white/5 hover:text-slate-900 dark:hover:text-slate-200'
                )}
              >
                <div className="relative shrink-0">
                  <Icon size={17} />
                  {showBadge && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-red-500 px-0.5 text-[8px] font-bold text-white">
                      {pendingTaskCount > 9 ? '9+' : pendingTaskCount}
                    </span>
                  )}
                  {errorCount > 0 && tab.id === 'settings' && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-red-500 px-0.5 text-[8px] font-bold text-white">
                      {errorCount > 9 ? '9+' : errorCount}
                    </span>
                  )}
                </div>
                <span className="flex-1">{tab.label}</span>
                {isMgmt && (
                  <ChevronDown
                    size={14}
                    className={cn(
                      'transition-transform duration-200 text-slate-400',
                      mgmtExpanded && 'rotate-180'
                    )}
                  />
                )}
              </button>

              {/* Management sub-items */}
              {isMgmt && (
                <AnimatePresence initial={false}>
                  {mgmtExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.18, ease: 'easeInOut' }}
                      className="overflow-hidden"
                    >
                      <div className="mt-0.5 space-y-0.5 pb-1">
                        {MGMT_SUBTABS.map((sub) => {
                          const SubIcon = sub.icon;
                          const isSubActive = activeTab === 'management' && mgmtSubTab === sub.id;
                          return (
                            <button
                              key={sub.id}
                              onClick={() => {
                                setActiveTab('management');
                                setMgmtSubTab(sub.id);
                              }}
                              className={cn(
                                'w-full flex items-center gap-2.5 pl-9 pr-3 py-2 rounded-xl text-xs font-medium transition-all duration-150',
                                isSubActive
                                  ? 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                                  : 'text-slate-500 dark:text-slate-500 hover:bg-slate-100/60 dark:hover:bg-white/5 hover:text-slate-800 dark:hover:text-slate-300'
                              )}
                            >
                              <SubIcon size={13} className="shrink-0" />
                              {sub.label}
                            </button>
                          );
                        })}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              )}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="shrink-0 border-t border-[var(--glass-border)] p-3 space-y-3">
        <ThemeSwitcher theme={theme} setTheme={setTheme} />
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/60 text-xs font-bold text-indigo-600 dark:text-indigo-400">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
              {user?.full_name ?? user?.username}
            </p>
            <p className="text-[10px] text-slate-400">{roleLabel[userRole] ?? userRole}</p>
          </div>
          <button
            onClick={onLogout}
            aria-label="Delogare"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-colors"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
