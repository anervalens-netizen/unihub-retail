import type { ReactNode } from "react";
import { ChevronDown, RefreshCw, Search } from "lucide-react";
import type { AgentListItem } from "../../api/agents";
import { ExportTableButton } from "../../components/ExportTableButton";
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from "../../lib/filterValues";
import type { AgentsListViewProps } from "./agentsOverviewTypes";

const nf = new Intl.NumberFormat("ro-RO", {
  style: "currency",
  currency: "RON",
  maximumFractionDigits: 0,
});
const nfNum = new Intl.NumberFormat("ro-RO");
const LIST_TABS = [
  { key: "active" as const, label: "Activi" },
  { key: "movement" as const, label: "Miscari" },
  { key: "inactive" as const, label: "Inactiv" },
  { key: "churned" as const, label: "Iesiti" },
  { key: "all" as const, label: ALL_SCOPE },
];

export function AgentsListView({
  currentMonth,
  list,
  filteredList,
  loadingList,
  activeTab,
  setActiveTab,
  search,
  setSearch,
  cardFirma,
  setCardFirma,
  cardMagazin,
  setCardMagazin,
  filterOptions,
  setSelectedAgent,
  listSectionRef,
}: AgentsListViewProps) {
  const storeNames = Array.from(
    new Set(
      filterOptions?.magazine
        .filter((store) => cardFirma === ALL_FIRMS || store.firma === cardFirma)
        .map((store) => store.locatie || store.site_code) || [],
    ),
  ).sort();

  return (
    <div ref={listSectionRef} className="glass scroll-mt-20 rounded-3xl p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">Lista Agenti</h3>
          <p className="text-[11px] text-slate-500">
            {filteredList.length === list.length
              ? `Toti (${list.length})`
              : `${filteredList.length} din ${list.length}`}{" "}
            {list.length === 200 ? "(maxim 200)" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {loadingList && (
            <RefreshCw size={14} className="animate-spin text-slate-400" />
          )}
          <ExportTableButton
            filename={`agenti_${currentMonth}`}
            sheetName={`Agenti ${currentMonth}`}
            rows={filteredList}
            columns={EXPORT_COLUMNS}
          />
        </div>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {LIST_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={tabClassName(activeTab === tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <label className="mb-4 flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-700 dark:bg-slate-800">
        <Search size={16} className="text-slate-400" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Cauta dupa nume agent..."
          className="w-full bg-transparent outline-none placeholder:text-slate-400"
        />
      </label>
      <div className="mb-4 grid grid-cols-2 gap-2">
        <FilterSelect
          label="Firma"
          value={cardFirma}
          onChange={(value) => {
            setCardFirma(value);
            setCardMagazin(ALL_STORES);
          }}
        >
          <option value={ALL_FIRMS}>Toate firmele</option>
          {filterOptions?.firme.sort().map((firma) => (
            <option key={firma} value={firma}>
              {firma}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect
          label="Magazin"
          value={cardMagazin}
          disabled={!filterOptions}
          onChange={setCardMagazin}
        >
          <option value={ALL_STORES}>Toate</option>
          {storeNames.map((locatie) => (
            <option key={locatie} value={locatie}>
              {locatie}
            </option>
          ))}
        </FilterSelect>
      </div>
      <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
        {filteredList.length === 0 && !loadingList ? (
          <div className="py-8 text-center text-sm text-slate-500">
            Niciun agent in aceasta categorie
          </div>
        ) : (
          filteredList.map((agent) => (
            <AgentRow
              key={agent.agent}
              agent={agent}
              onSelect={setSelectedAgent}
            />
          ))
        )}
      </div>
    </div>
  );
}

const EXPORT_COLUMNS = [
  { header: "Agent", value: (row: AgentListItem) => row.agent },
  { header: "Firma", value: (row: AgentListItem) => row.firma ?? "" },
  { header: "Magazin", value: (row: AgentListItem) => row.store_name ?? "" },
  { header: "Status", value: (row: AgentListItem) => row.current_status },
  { header: "Nou", value: (row: AgentListItem) => (row.is_new ? "Da" : "Nu") },
  {
    header: "Reactivat",
    value: (row: AgentListItem) => (row.is_reactivated ? "Da" : "Nu"),
  },
  {
    header: "Vanzari",
    value: (row: AgentListItem) => row.total_sales,
    format: "currency" as const,
  },
  {
    header: "Cantitate",
    value: (row: AgentListItem) => row.total_quantity,
    format: "integer" as const,
  },
];

function tabClassName(selected: boolean) {
  return `rounded-xl px-3 py-1.5 text-xs font-bold transition-colors ${
    selected
      ? "bg-indigo-500 text-white"
      : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
  }`;
}

function FilterSelect({
  label,
  value,
  onChange,
  disabled,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-bold uppercase text-slate-500">
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 pr-6 text-xs outline-none disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800"
        >
          {children}
        </select>
        <ChevronDown
          size={12}
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400"
        />
      </div>
    </div>
  );
}

function AgentRow({
  agent,
  onSelect,
}: {
  agent: AgentListItem;
  onSelect: (agent: string) => void;
}) {
  return (
    <button
      onClick={() => onSelect(agent.agent)}
      className="flex w-full items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-left transition-colors hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800"
    >
      <div>
        <div className="font-bold text-slate-800 dark:text-slate-200">
          {agent.agent}
        </div>
        {agent.store_name && (
          <div className="text-[10px] text-slate-500">{agent.store_name}</div>
        )}
        <div className="mt-1 flex items-center gap-2">
          {agent.current_status === "active" && (
            <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
              ACTIV
            </span>
          )}
          {agent.current_status === "inactive_recent" && (
            <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400">
              INACTIV RECENT
            </span>
          )}
          {agent.current_status === "churned" && (
            <span className="text-[10px] font-bold text-rose-600 dark:text-rose-400">
              IESIT
            </span>
          )}
          {agent.is_new && (
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
              Nou
            </span>
          )}
          {agent.is_reactivated && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
              Reactivat
            </span>
          )}
        </div>
      </div>
      <div className="text-right">
        <div className="text-sm font-black">{nf.format(agent.total_sales)}</div>
        <div className="text-[10px] text-slate-500">
          {nfNum.format(agent.total_quantity)} buc
        </div>
      </div>
    </button>
  );
}
