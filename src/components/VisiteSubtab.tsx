import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  MapPin,
  X,
  XCircle,
} from 'lucide-react';
import {
  getVisitDetail,
  getVisitPhotoUrl,
  getVisitsReport,
  getVisitsTree,
  type TeamLeaderGroup,
  type VisitDetail,
  type VisitReportResponse,
  type VisitSummaryItem,
} from '../api/visitsReport';
import { client } from '../api/client';
import type { AppFilters } from './MainLayout';
import { cn } from '../lib/utils';

// ── AuthImage — fetch cu token, afișează blob URL ─────────────────────────────
function AuthImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let url: string | null = null;
    client.get<Blob>(src, { responseType: 'blob' }).then((r) => {
      url = URL.createObjectURL(r.data);
      setBlobUrl(url);
    }).catch(() => setBlobUrl(null));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [src]);

  if (!blobUrl) {
    return (
      <div className={cn('animate-pulse bg-slate-200 dark:bg-slate-700', className)} />
    );
  }
  return <img src={blobUrl} alt={alt} className={className} />;
}

interface VisiteSubtabProps {
  currentMonth: string;
  filters: AppFilters;
}

// ── small helpers ─────────────────────────────────────────────────────────────

function PctBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 50 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
      <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${value}%` }} />
    </div>
  );
}

function CompletionBadge({ pct }: { pct: number }) {
  return (
    <span
      className={cn(
        'inline-block rounded-full px-2 py-0.5 text-[10px] font-bold',
        pct >= 80
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
          : pct >= 50
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
            : 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300'
      )}
    >
      {pct}%
    </span>
  );
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      {value ? (
        <CheckCircle2 size={15} className="text-emerald-500" />
      ) : (
        <XCircle size={15} className="text-red-400" />
      )}
    </div>
  );
}

function NumRow({ label, value }: { label: string; value: number | null | undefined }) {
  if (value == null) return null;
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
        {value.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
      </span>
    </div>
  );
}

// ── visit drawer ──────────────────────────────────────────────────────────────

function VisitDrawer({
  visitId,
  onClose,
}: {
  visitId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<VisitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [photoIdx, setPhotoIdx] = useState(0);
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    setDetail(null);
    setPhotoIdx(0);
    getVisitDetail(visitId)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [visitId]);

  // close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm">
      <div
        ref={drawerRef}
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-2xl dark:bg-slate-900"
      >
        {/* header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
              Detalii Vizita
            </p>
            {detail && (
              <p className="text-sm font-bold text-slate-800 dark:text-slate-100">
                {detail.magazin} · {detail.data_raport}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
            Se incarca...
          </div>
        )}

        {!loading && detail && (
          <div className="flex-1 space-y-4 p-4">
            {/* photos */}
            {detail.photos.length > 0 && (
              <div className="overflow-hidden rounded-2xl bg-slate-100 dark:bg-slate-800">
                <AuthImage
                  src={getVisitPhotoUrl(detail.id, detail.photos[photoIdx])}
                  alt={`foto ${photoIdx + 1}`}
                  className="h-56 w-full object-cover"
                />
                {detail.photos.length > 1 && (
                  <div className="flex gap-1.5 overflow-x-auto p-2">
                    {detail.photos.map((f, i) => (
                      <button key={f} onClick={() => setPhotoIdx(i)}>
                        <AuthImage
                          src={getVisitPhotoUrl(detail.id, f)}
                          alt={`thumb ${i + 1}`}
                          className={cn(
                            'h-12 w-12 rounded-lg object-cover ring-2 transition-all',
                            i === photoIdx
                              ? 'ring-indigo-500'
                              : 'ring-transparent opacity-60 hover:opacity-100'
                          )}
                        />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* meta */}
            <div className="glass rounded-2xl p-4">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  General
                </h4>
                <CompletionBadge pct={detail.completion_pct} />
              </div>
              <div className="space-y-0">
                {detail.team_leader && (
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800">
                    <span className="text-xs text-slate-500">Team Leader</span>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {detail.team_leader}
                    </span>
                  </div>
                )}
                {detail.asm && (
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800">
                    <span className="text-xs text-slate-500">ASM</span>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {detail.asm}
                    </span>
                  </div>
                )}
                <NumRow label="Durata (ore)" value={detail.durata_vizita_ore} />
                {detail.ora_trimitere && (
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800">
                    <span className="text-xs text-slate-500">Ora</span>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {detail.ora_trimitere}
                    </span>
                  </div>
                )}
                {detail.firma && (
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800">
                    <span className="text-xs text-slate-500">Firma</span>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {detail.firma}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* compliance */}
            <div className="glass rounded-2xl p-4">
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                Conformitate
              </h4>
              <BoolRow label="Curatenie" value={detail.curatenie} />
              <BoolRow label="Imagine" value={detail.imagine} />
              <BoolRow label="Uniforma" value={detail.uniforma} />
              <BoolRow label="Afise" value={detail.afise} />
              <BoolRow label="Produse promo" value={detail.produse_promo} />
              <BoolRow label="Avizat" value={detail.avizat} />
            </div>

            {/* financiar */}
            {(detail.tpu != null || detail.sticla != null || detail.charisma != null ||
              detail.casa != null || detail.incarcari_epay != null) && (
              <div className="glass rounded-2xl p-4">
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                  Financiar
                </h4>
                <NumRow label="TPU" value={detail.tpu} />
                <NumRow label="Sticla" value={detail.sticla} />
                <NumRow label="Altele" value={detail.altele} />
                <NumRow label="Charisma" value={detail.charisma} />
                <NumRow label="Casa" value={detail.casa} />
                <NumRow label="Incarcari ePay" value={detail.incarcari_epay} />
                <NumRow label="Incarcari Charisma" value={detail.incarcari_charisma} />
              </div>
            )}

            {/* agenti */}
            {[
              { nume: detail.agent1_nume, perf: detail.agent1_perf, doi: detail.agent1_doi_pe_bon, focus: detail.agent1_focus, analiza: detail.agent1_analiza, plan: detail.agent1_plan },
              { nume: detail.agent2_nume, perf: detail.agent2_perf, doi: detail.agent2_doi_pe_bon, focus: detail.agent2_focus, analiza: detail.agent2_analiza, plan: detail.agent2_plan },
            ]
              .filter((a) => a.nume)
              .map((a, idx) => (
                <div key={idx} className="glass rounded-2xl p-4">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                    Agent — {a.nume}
                  </h4>
                  <NumRow label="Performanta" value={a.perf} />
                  <NumRow label="Doi pe bon" value={a.doi} />
                  <NumRow label="Focus" value={a.focus} />
                  {a.analiza && (
                    <div className="mt-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
                      <p className="mb-1 text-[10px] font-bold uppercase text-slate-400">Analiza</p>
                      <p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
                        {a.analiza}
                      </p>
                    </div>
                  )}
                  {a.plan && (
                    <div className="mt-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
                      <p className="mb-1 text-[10px] font-bold uppercase text-slate-400">Plan</p>
                      <p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
                        {a.plan}
                      </p>
                    </div>
                  )}
                </div>
              ))}

            {/* notes */}
            {detail.notes && (
              <div className="glass rounded-2xl p-4">
                <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                  Note
                </h4>
                <p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
                  {detail.notes}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── visit row inside a day ────────────────────────────────────────────────────

function VisitRow({ visit, onOpen }: { visit: VisitSummaryItem; onOpen: (id: string) => void }) {
  return (
    <button
      onClick={() => onOpen(visit.id)}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-indigo-50 dark:hover:bg-indigo-900/20"
    >
      <MapPin size={14} className="shrink-0 text-indigo-400" />
      <span className="flex-1 text-xs font-semibold text-slate-700 dark:text-slate-200">
        {visit.magazin || '—'}
      </span>
      {visit.ora && (
        <span className="text-[10px] text-slate-400">{visit.ora.slice(0, 5)}</span>
      )}
      {visit.has_photos && <Camera size={12} className="text-slate-400" />}
      <CompletionBadge pct={visit.completion_pct} />
    </button>
  );
}

// ── day accordion ─────────────────────────────────────────────────────────────

function DayRow({
  day,
  onOpenVisit,
}: {
  day: import('../api/visitsReport').VisitDayGroup;
  onOpenVisit: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const label = day.date === '—' ? '—' : new Date(day.date + 'T12:00:00').toLocaleDateString('ro-RO', { day: 'numeric', month: 'long' });

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800"
      >
        {open ? (
          <ChevronDown size={13} className="shrink-0 text-slate-400" />
        ) : (
          <ChevronRight size={13} className="shrink-0 text-slate-400" />
        )}
        <span className="flex-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          {label}
        </span>
        <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-700">
          {day.nr_vizite}
        </span>
      </button>
      {open && (
        <div className="ml-5 space-y-0.5 pb-1">
          {day.visits.map((v) => (
            <VisitRow key={v.id} visit={v} onOpen={onOpenVisit} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── month accordion ───────────────────────────────────────────────────────────

function MonthRow({
  month,
  onOpenVisit,
}: {
  month: import('../api/visitsReport').VisitMonthGroup;
  onOpenVisit: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const label = month.month === '—' ? '—' : new Date(month.month + '-01').toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' });

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800"
      >
        {open ? (
          <ChevronDown size={14} className="shrink-0 text-indigo-400" />
        ) : (
          <ChevronRight size={14} className="shrink-0 text-indigo-400" />
        )}
        <span className="flex-1 text-sm font-semibold capitalize text-slate-700 dark:text-slate-200">
          {label}
        </span>
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
          {month.nr_vizite} viz.
        </span>
      </button>
      {open && (
        <div className="ml-4 space-y-0.5 border-l border-slate-100 pl-2 dark:border-slate-800">
          {month.days.map((d) => (
            <DayRow key={d.date} day={d} onOpenVisit={onOpenVisit} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Team Leader accordion ─────────────────────────────────────────────────────

function TeamLeaderRow({
  group,
  onOpenVisit,
}: {
  group: TeamLeaderGroup;
  onOpenVisit: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-slate-100 last:border-0 dark:border-slate-800">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
      >
        <div
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-black',
            open
              ? 'bg-indigo-600 text-white'
              : 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300'
          )}
        >
          {group.team_leader.charAt(0).toUpperCase()}
        </div>
        <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
          {group.team_leader}
        </span>
        <span className="text-xs text-slate-400">{group.nr_vizite} viz.</span>
        {open ? (
          <ChevronDown size={15} className="text-slate-400" />
        ) : (
          <ChevronRight size={15} className="text-slate-400" />
        )}
      </button>
      {open && (
        <div className="space-y-0.5 pb-2 pl-4 pr-2">
          {group.months.map((m) => (
            <MonthRow key={m.month} month={m} onOpenVisit={onOpenVisit} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── compliance summary cards ──────────────────────────────────────────────────

const COMPLIANCE_KEYS: Array<{ key: keyof import('../api/visitsReport').VisitReportRow; label: string }> = [
  { key: 'curatenie_pct', label: 'Curatenie' },
  { key: 'imagine_pct', label: 'Imagine' },
  { key: 'uniforma_pct', label: 'Uniforma' },
  { key: 'afise_pct', label: 'Afise' },
  { key: 'produse_promo_pct', label: 'Promo' },
];

// ── month picker ──────────────────────────────────────────────────────────────

function MonthPicker({
  months,
  selected,
  onChange,
}: {
  months: string[];
  selected: string;
  onChange: (m: string) => void;
}) {
  if (months.length === 0) return null;
  return (
    <select
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
    >
      {months.map((m) => {
        const label = new Date(m + '-01').toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' });
        return (
          <option key={m} value={m}>
            {label.charAt(0).toUpperCase() + label.slice(1)}
          </option>
        );
      })}
    </select>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function VisiteSubtab({ currentMonth, filters }: VisiteSubtabProps) {
  const [summary, setSummary] = useState<VisitReportResponse | null>(null);
  const [groups, setGroups] = useState<TeamLeaderGroup[]>([]);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingTree, setLoadingTree] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openVisitId, setOpenVisitId] = useState<string | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<string>(currentMonth);

  // extract sorted months from tree data
  const availableMonths = useMemo(() => {
    const set = new Set<string>();
    groups.forEach((g) => g.months.forEach((m) => set.add(m.month)));
    return Array.from(set).sort().reverse();
  }, [groups]);

  // when tree loads, default to the latest month with visits
  useEffect(() => {
    if (availableMonths.length > 0 && !availableMonths.includes(selectedMonth)) {
      setSelectedMonth(availableMonths[0]);
    }
  }, [availableMonths, selectedMonth]);

  useEffect(() => {
    setLoadingSummary(true);
    setError(null);
    getVisitsReport(selectedMonth, filters)
      .then(setSummary)
      .catch((e: Error) => setError(e.message || 'Eroare la incarcare'))
      .finally(() => setLoadingSummary(false));
  }, [selectedMonth, filters]);

  useEffect(() => {
    setLoadingTree(true);
    getVisitsTree(filters)
      .then((r) => setGroups(r.team_leaders))
      .catch(() => setGroups([]))
      .finally(() => setLoadingTree(false));
  }, [filters]);

  // filter tree client-side to selected month
  const filteredGroups = useMemo(() => {
    return groups
      .map((g) => ({
        ...g,
        months: g.months.filter((m) => m.month === selectedMonth),
      }))
      .filter((g) => g.months.length > 0)
      .map((g) => ({
        ...g,
        nr_vizite: g.months.reduce((s, m) => s + m.nr_vizite, 0),
      }));
  }, [groups, selectedMonth]);

  if (loadingTree && loadingSummary) {
    return (
      <div className="flex h-40 items-center justify-center text-sm font-semibold text-slate-500">
        Se incarca vizitele...
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-4 mt-4 rounded-2xl bg-red-50 p-4 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
        {error}
      </div>
    );
  }

  if (!loadingTree && availableMonths.length === 0) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 text-slate-400">
        <MapPin size={28} strokeWidth={1.5} />
        <p className="text-sm font-semibold">Nicio vizita inregistrata</p>
      </div>
    );
  }

  const avgCompliance =
    summary && summary.rows.length > 0
      ? COMPLIANCE_KEYS.reduce((acc, { key }) => {
          const vals = summary.rows.map((r) => r[key] as number);
          return { ...acc, [key]: vals.reduce((a, b) => a + b, 0) / vals.length };
        }, {} as Record<string, number>)
      : {};

  return (
    <div className="space-y-4 px-4">
      {/* Month picker */}
      <MonthPicker months={availableMonths} selected={selectedMonth} onChange={setSelectedMonth} />

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-2">
        <div className="glass rounded-2xl p-3 text-center">
          <div className="text-2xl font-black text-indigo-600">
            {loadingSummary ? '—' : (summary?.total_vizite ?? 0)}
          </div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Vizite
          </div>
        </div>
        <div className="glass rounded-2xl p-3 text-center">
          <div className="text-2xl font-black text-indigo-600">
            {loadingSummary ? '—' : (summary?.magazine_unice ?? 0)}
          </div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Magazine
          </div>
        </div>
        <div className="glass rounded-2xl p-3 text-center">
          <div
            className={cn(
              'text-2xl font-black',
              (summary?.avg_completion ?? 0) >= 80
                ? 'text-emerald-600'
                : (summary?.avg_completion ?? 0) >= 50
                  ? 'text-amber-500'
                  : 'text-red-500'
            )}
          >
            {loadingSummary ? '—' : `${(summary?.avg_completion ?? 0).toFixed(0)}%`}
          </div>
          <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Completare
          </div>
        </div>
      </div>

      {/* Compliance bars */}
      {summary && summary.rows.length > 0 && (
        <div className="glass rounded-2xl p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">
            Conformitate medie — {selectedMonth}
          </h3>
          <div className="space-y-2">
            {COMPLIANCE_KEYS.map(({ key, label }) => {
              const avg = avgCompliance[key] ?? 0;
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-20 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                    {label}
                  </span>
                  <div className="flex-1">
                    <PctBar value={avg} />
                  </div>
                  <span className="w-10 text-right text-[11px] font-bold text-slate-700 dark:text-slate-200">
                    {avg.toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Team Leader accordion */}
      <div className="glass overflow-hidden rounded-2xl">
        <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
            Vizite pe Team Leader
          </h3>
        </div>
        {loadingTree ? (
          <div className="flex h-16 items-center justify-center text-xs text-slate-400">
            Se incarca...
          </div>
        ) : filteredGroups.length === 0 ? (
          <div className="flex h-16 items-center justify-center text-xs text-slate-400">
            Nicio vizita pentru luna selectata
          </div>
        ) : (
          <div>
            {filteredGroups.map((g) => (
              <TeamLeaderRow key={g.team_leader} group={g} onOpenVisit={setOpenVisitId} />
            ))}
          </div>
        )}
        <div className="px-4 py-2 text-[10px] text-slate-400">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> ≥80%
          </span>
          <span className="mx-2 inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-400" /> 50–79%
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-400" /> &lt;50%
          </span>
        </div>
      </div>

      {/* Visit detail drawer */}
      {openVisitId && (
        <VisitDrawer visitId={openVisitId} onClose={() => setOpenVisitId(null)} />
      )}
    </div>
  );
}
