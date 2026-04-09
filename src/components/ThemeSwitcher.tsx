import { Moon, Sun, SunMoon } from 'lucide-react';
import { cn } from '../lib/utils';

const THEMES = [
  { id: 'light', icon: Sun, label: 'Light' },
  { id: 'light-mint', icon: SunMoon, label: 'Mint' },
  { id: 'light-olive', icon: SunMoon, label: 'Olive' },
  { id: 'dark', icon: Moon, label: 'Dark' },
];

export function ThemeSwitcher({ theme, setTheme }: { theme: string; setTheme: (theme: string) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
      {THEMES.map((item) => {
        const Icon = item.icon;
        const isActive = theme === item.id;
        return (
          <button
            key={item.id}
            onClick={() => setTheme(item.id)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-xl text-xs transition-all',
              isActive
                ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-indigo-400'
                : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
            )}
            title={item.label}
          >
            <Icon size={14} />
          </button>
        );
      })}
    </div>
  );
}
