import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import { ALL_TABS, MGMT_SUBTABS, type ManagementTab, type TabId } from '../lib/tabs';
import { ThemeSwitcher } from './ThemeSwitcher';
import { cn } from '../lib/utils';

interface Props {
  activeTab: string;
  setActiveTab: (tab: TabId) => void;
  mgmtSubTab: ManagementTab;
  setMgmtSubTab: (tab: ManagementTab) => void;
  theme: string;
  setTheme: (theme: string) => void;
  errorCount?: number;
}

export function DesktopSidebar({
  activeTab,
  setActiveTab,
  mgmtSubTab,
  setMgmtSubTab,
  theme,
  setTheme,
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

  return (
    <aside className="hidden lg:flex flex-col h-full w-60 shrink-0 border-r border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl z-40">
      {/* Header */}
      <div className="flex items-center gap-2.5 h-14 px-4 border-b border-[var(--glass-border)] shrink-0">
        <img
          src="/logo-mark.png"
          alt=""
          className="h-7 w-7 shrink-0 rounded-lg bg-white p-0.5 shadow-sm"
          aria-hidden
        />
        <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100">
          UniHub Retail
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {ALL_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
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
      <div className="shrink-0 border-t border-[var(--glass-border)] p-3">
        <ThemeSwitcher theme={theme} setTheme={setTheme} />
      </div>
    </aside>
  );
}
