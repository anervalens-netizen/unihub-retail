import { ChevronDown, ChevronUp, RefreshCw, Store } from "lucide-react";
import type { StoreCoverageItem } from "../../api/agents";
import type {
  AgentsCoverageViewProps,
  ExpandedCoverageSection,
} from "./agentsOverviewTypes";

const COVERAGE_CARDS: Array<{
  section: Exclude<ExpandedCoverageSection, null>;
  label: string;
  tone: string;
  iconTone: string;
  valueTone: string;
  hint?: string;
}> = [
  {
    section: "active",
    label: "Active",
    tone: "bg-emerald-50/50 dark:bg-emerald-900/10 hover:bg-emerald-100/60 dark:hover:bg-emerald-900/20",
    iconTone: "text-emerald-500",
    valueTone: "text-emerald-600 dark:text-emerald-400",
  },
  {
    section: "modified",
    label: "Cu Modificări",
    tone: "bg-amber-50/50 dark:bg-amber-900/10 hover:bg-amber-100/60 dark:hover:bg-amber-900/20",
    iconTone: "text-amber-500",
    valueTone: "text-amber-600 dark:text-amber-400",
    hint: "intrari / iesiri agenti",
  },
  {
    section: "inactive",
    label: "Inactive",
    tone: "bg-slate-50/80 dark:bg-slate-800/40 hover:bg-slate-100/60 dark:hover:bg-slate-800/60",
    iconTone: "text-slate-500",
    valueTone: "",
    hint: "> 3 luni fara activitate",
  },
];

export function AgentsCoverageView({
  coverage,
  loadingCoverage,
  expandedSection,
  setExpandedSection,
  coverageSectionRef,
}: AgentsCoverageViewProps) {
  const countFor = (section: Exclude<ExpandedCoverageSection, null>) => {
    if (!coverage) return "-";
    return section === "active"
      ? coverage.active_stores_count
      : section === "modified"
        ? coverage.modified_stores_count
        : coverage.closed_stores_count;
  };

  return (
    <div
      ref={coverageSectionRef}
      className="glass scroll-mt-20 rounded-3xl p-4"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">Magazine si Flux</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            Acoperire agenti pe magazine
          </p>
        </div>
        {loadingCoverage && (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
            <RefreshCw size={14} className="animate-spin text-slate-400" />
          </div>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {COVERAGE_CARDS.map((card) => (
          <button
            key={card.section}
            onClick={() =>
              setExpandedSection((previous) =>
                previous === card.section ? null : card.section,
              )
            }
            className={`rounded-2xl p-3 text-left transition-colors ${card.tone}`}
          >
            <div className="mb-2 flex items-center justify-between gap-1">
              <div className="flex items-center gap-2">
                <Store size={16} className={card.iconTone} />
                <div className="text-xs font-bold text-slate-600 dark:text-slate-400">
                  {card.label}
                </div>
              </div>
              {expandedSection === card.section ? (
                <ChevronUp size={12} className="shrink-0 text-slate-400" />
              ) : (
                <ChevronDown size={12} className="shrink-0 text-slate-400" />
              )}
            </div>
            <div className={`text-2xl font-black ${card.valueTone}`}>
              {countFor(card.section)}
            </div>
            {card.hint && (
              <div className="mt-1 text-[10px] text-slate-500">{card.hint}</div>
            )}
          </button>
        ))}
      </div>
      {coverage && expandedSection === "active" && (
        <CoverageList
          title={`Magazine active (${coverage.active_stores_count})`}
          items={coverage.items.filter((item) => item.status === "covered")}
          tone="emerald"
        />
      )}
      {coverage && expandedSection === "modified" && (
        <CoverageList
          title={`Magazine cu modificări (${coverage.modified_stores_count})`}
          items={coverage.items.filter((item) => item.has_changes)}
          tone="amber"
        />
      )}
      {coverage &&
        expandedSection === "inactive" &&
        coverage.closed_stores_count > 0 && (
          <CoverageList
            title={`Magazine inactive (${coverage.closed_stores_count}) — > 3 luni fara activitate`}
            items={coverage.items.filter((item) => item.status === "closed")}
            tone="slate"
          />
        )}
    </div>
  );
}

function CoverageList({
  title,
  items,
  tone,
}: {
  title: string;
  items: StoreCoverageItem[];
  tone: "emerald" | "amber" | "slate";
}) {
  return (
    <div className="mt-3 max-h-56 space-y-1 overflow-y-auto">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
        {title}
      </div>
      {items.map((item) => (
        <CoverageRow key={item.site_code} item={item} tone={tone} />
      ))}
    </div>
  );
}

function CoverageRow({
  item,
  tone,
}: {
  item: StoreCoverageItem;
  tone: "emerald" | "amber" | "slate";
}) {
  if (tone === "amber")
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl bg-amber-50/50 px-3 py-2 dark:bg-amber-900/10">
        <div className="min-w-0 flex-1">
          <span className="block truncate text-xs font-bold text-slate-700 dark:text-slate-200">
            {item.locatie || item.site_code}
          </span>
          <span className="text-[10px] text-slate-400">
            {item.asm} · {item.change_reason || "modificat"} ·{" "}
            {item.previous_agent_count} → {item.agent_count} ag.
          </span>
        </div>
        <div className="ml-2 flex shrink-0 items-center gap-1">
          {item.added_agents_count > 0 && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              +{item.added_agents_count}
            </span>
          )}
          {item.removed_agents_count > 0 && (
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
              -{item.removed_agents_count}
            </span>
          )}
        </div>
      </div>
    );
  if (tone === "slate")
    return (
      <div className="flex items-center justify-between rounded-xl bg-slate-100/60 px-3 py-2 dark:bg-slate-800/40">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-xs font-bold text-slate-600 dark:text-slate-300">
              {item.locatie || item.site_code}
            </span>
            <span className="shrink-0 text-[10px] text-slate-400">
              {item.asm}
            </span>
          </div>
          <div className="text-[10px] text-slate-400">
            {item.firma} · {item.regional}
          </div>
        </div>
        <span className="ml-2 shrink-0 text-[10px] font-bold text-slate-400">
          {item.agent_count} ag.
        </span>
      </div>
    );
  return (
    <div className="flex items-center justify-between rounded-xl bg-emerald-50/50 px-3 py-2 dark:bg-emerald-900/10">
      <div className="min-w-0 flex-1">
        <span className="block truncate text-xs font-bold text-slate-700 dark:text-slate-200">
          {item.locatie || item.site_code}
        </span>
        <span className="text-[10px] text-slate-400">{item.asm}</span>
      </div>
      <span className="ml-2 shrink-0 text-[10px] font-bold text-emerald-600">
        {item.agent_count} ag.
      </span>
    </div>
  );
}
