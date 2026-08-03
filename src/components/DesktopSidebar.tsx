import { ALL_TABS, type TabId } from '../lib/tabs';
import { ThemeSwitcher } from './ThemeSwitcher';
import { cn } from '../lib/utils';

interface Props {
  activeTab: string;
  setActiveTab: (tab: TabId) => void;
  theme: string;
  setTheme: (theme: string) => void;
  errorCount?: number;
  canAccessManagement?: boolean;
}

export function DesktopSidebar({
  activeTab,
  setActiveTab,
  theme,
  setTheme,
  errorCount = 0,
  canAccessManagement = true,
}: Props) {
  return (
    <aside className="hidden lg:flex flex-col h-full w-60 shrink-0 border-r border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl z-40">
      {/* Header */}
      <div className="flex items-center gap-2.5 h-14 px-4 border-b border-[var(--glass-border)] shrink-0">
        <img
          src="/favicon-64.png"
          alt=""
          className="h-7 w-7 shrink-0 rounded-lg bg-white p-0.5 shadow-sm"
          aria-hidden
          decoding="async"
        />
        <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100">
          UniHub Retail
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {ALL_TABS.filter((tab) => canAccessManagement || tab.id !== 'management').map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <div key={tab.id}>
              <button
                onClick={() => setActiveTab(tab.id as TabId)}
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
              </button>
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
