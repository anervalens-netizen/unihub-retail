import type { ComponentType } from "react";
import type { CampaignPromotionOption, ContestResponse } from "../../api/generated/runtime-types";

export function CampaignMonthBar({
  title,
  icon: Icon,
  months,
  value,
  onChange,
  currentMonth,
}: {
  title: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  months: string[];
  value: string;
  onChange: (month: string) => void;
  currentMonth: string;
}) {
  return (
    <div className="glass flex items-center justify-between rounded-3xl p-3">
      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
        <Icon size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          {title}
        </span>
      </div>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs font-bold text-amber-700 dark:border-amber-800 dark:bg-slate-800 dark:text-amber-300"
      >
        {months.map((month) => (
          <option key={month} value={month}>
            {month}
            {month === currentMonth ? " (curent)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

export function EmptyCard({ message }: { message: string }) {
  return (
    <div className="glass rounded-3xl p-6 text-sm font-semibold text-slate-500">
      {message}
    </div>
  );
}

export function ContestSelector({
  contests,
  selectedKey,
  onSelect,
}: {
  contests: ContestResponse[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="glass sticky top-2 z-20 grid grid-cols-2 gap-1 rounded-2xl p-1">
      {contests.map((contest) => (
        <button
          key={contest.key}
          type="button"
          onClick={() => onSelect(contest.key)}
          title={contest.scope_label || contest.title}
          className={`min-w-0 rounded-xl px-3 py-2 text-xs font-bold transition-all ${selectedKey === contest.key ? "bg-white text-amber-700 shadow-sm dark:bg-slate-800 dark:text-amber-300" : "text-slate-500 hover:bg-white/60 dark:hover:bg-slate-800/60"}`}
        >
          <span className="block truncate">
            {contest.scope_label || contest.title}
          </span>
        </button>
      ))}
    </div>
  );
}

export function PromotionSelector({
  promotions,
  selectedKey,
  onSelect,
}: {
  promotions: CampaignPromotionOption[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="glass grid grid-cols-1 gap-1 rounded-2xl p-1 sm:grid-cols-3">
      {promotions.map((promotion) => (
        <button
          key={promotion.key}
          type="button"
          onClick={() => onSelect(promotion.key)}
          title={promotion.label}
          className={`min-w-0 rounded-xl px-3 py-2 text-xs font-bold transition-all ${selectedKey === promotion.key ? "bg-white text-amber-700 shadow-sm dark:bg-slate-800 dark:text-amber-300" : "text-slate-500 hover:bg-white/60 dark:hover:bg-slate-800/60"}`}
        >
          <span className="block truncate">{promotion.label}</span>
        </button>
      ))}
    </div>
  );
}
