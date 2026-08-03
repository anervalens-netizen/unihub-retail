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
    <aside className="hidden h-dvh w-52 shrink-0 flex-col border-r border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl lg:sticky lg:top-0 lg:flex xl:w-56 z-40">
      {/* Header */}
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-[var(--glass-border)] px-4">
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
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {ALL_TABS.filter((tab) => canAccessManagement || tab.id !== 'management').map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <div key={tab.id}>
              <button
                onClick={() => setActiveTab(tab.id as TabId)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition-all duration-150',
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
