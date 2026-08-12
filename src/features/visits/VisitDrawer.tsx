import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, X, XCircle } from 'lucide-react';

import { getVisitDetail, getVisitPhoto, type VisitDetail } from '../../api/visitsReport';
import { FirmaBadge } from '../../components/FirmaBadge';
import { cn } from '../../lib/utils';
import { queryKeys } from '../../lib/queryKeys';

function AuthImage({ visitId, filename, alt, className }: { visitId: string; filename: string; alt: string; className?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let url: string | null = null;
    getVisitPhoto(visitId, filename, controller.signal).then((blob) => { url = URL.createObjectURL(blob); setBlobUrl(url); }).catch(() => { if (!controller.signal.aborted) setBlobUrl(null); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [visitId, filename]);
  if (!blobUrl) return <div className={cn('animate-pulse bg-slate-200 dark:bg-slate-700', className)} />;
  return <img src={blobUrl} alt={alt} className={className} loading="lazy" decoding="async" />;
}

export function CompletionBadge({ pct }: { pct: number }) {
  const tone = pct >= 80 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : pct >= 50 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300';
  return <span className={cn('inline-block rounded-full px-2 py-0.5 text-[10px] font-bold', tone)}>{pct}%</span>;
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800 last:border-0"><span className="text-xs text-slate-500">{label}</span>{value ? <CheckCircle2 size={15} className="text-emerald-500" /> : <XCircle size={15} className="text-red-400" />}</div>;
}

function NumRow({ label, value }: { label: string; value: number | null | undefined }) {
  if (value == null) return null;
  return <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800 last:border-0"><span className="text-xs text-slate-500">{label}</span><span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{value.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</span></div>;
}

function VisitPhotos({ detail, photoIdx, onSelect }: { detail: VisitDetail; photoIdx: number; onSelect: (index: number) => void }) {
  const currentPhoto = detail.photos[photoIdx];
  if (!currentPhoto) return null;
  return (
    <div className="overflow-hidden rounded-2xl bg-slate-100 dark:bg-slate-800">
      <AuthImage visitId={detail.id} filename={currentPhoto} alt={`foto ${photoIdx + 1}`} className="h-56 w-full object-cover" />
      {detail.photos.length > 1 && <div className="flex gap-1.5 overflow-x-auto p-2">{detail.photos.map((filename, index) => <button key={filename} onClick={() => onSelect(index)}><AuthImage visitId={detail.id} filename={filename} alt={`thumb ${index + 1}`} className={cn('h-12 w-12 rounded-lg object-cover ring-2 transition-all', index === photoIdx ? 'ring-indigo-500' : 'ring-transparent opacity-60 hover:opacity-100')} /></button>)}</div>}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return <div className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-800"><span className="text-xs text-slate-500">{label}</span><span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{value}</span></div>;
}

function VisitGeneral({ detail }: { detail: VisitDetail }) {
  return <div className="glass rounded-2xl p-4"><div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">General</h4><CompletionBadge pct={detail.completion_pct} /></div><DetailRow label="Team Leader" value={detail.team_leader} /><DetailRow label="ASM" value={detail.asm} /><NumRow label="Durata (ore)" value={detail.durata_vizita_ore} /><DetailRow label="Ora" value={detail.ora_trimitere} /><DetailRow label="Firma" value={detail.firma} /></div>;
}

function VisitCompliance({ detail }: { detail: VisitDetail }) {
  return <div className="glass rounded-2xl p-4"><h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Conformitate</h4><BoolRow label="Curatenie" value={detail.curatenie} /><BoolRow label="Imagine" value={detail.imagine} /><BoolRow label="Uniforma" value={detail.uniforma} /><BoolRow label="Afise" value={detail.afise} /><BoolRow label="Produse promo" value={detail.produse_promo} /><BoolRow label="Avizat" value={detail.avizat} /></div>;
}

function VisitFinancial({ detail }: { detail: VisitDetail }) {
  if ([detail.tpu, detail.sticla, detail.charisma, detail.casa, detail.incarcari_epay].every((value) => value == null)) return null;
  return <div className="glass rounded-2xl p-4"><h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Financiar</h4><NumRow label="TPU" value={detail.tpu} /><NumRow label="Sticla" value={detail.sticla} /><NumRow label="Altele" value={detail.altele} /><NumRow label="Charisma" value={detail.charisma} /><NumRow label="Casa" value={detail.casa} /><NumRow label="Incarcari ePay" value={detail.incarcari_epay} /><NumRow label="Incarcari Charisma" value={detail.incarcari_charisma} /></div>;
}

type VisitAgent = { nume: string | null; perf: number | null; doi: number | null; focus: number | null; analiza: string | null; plan: string | null };

function AgentCard({ agent }: { agent: VisitAgent }) {
  return <div className="glass rounded-2xl p-4"><h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Agent — {agent.nume}</h4><NumRow label="Performanta" value={agent.perf} /><NumRow label="Doi pe bon" value={agent.doi} /><NumRow label="Focus" value={agent.focus} />{agent.analiza && <div className="mt-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800"><p className="mb-1 text-[10px] font-bold uppercase text-slate-400">Analiza</p><p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">{agent.analiza}</p></div>}{agent.plan && <div className="mt-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800"><p className="mb-1 text-[10px] font-bold uppercase text-slate-400">Plan</p><p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">{agent.plan}</p></div>}</div>;
}

function VisitDetails({ detail, photoIdx, onPhotoSelect }: { detail: VisitDetail; photoIdx: number; onPhotoSelect: (index: number) => void }) {
  const agents: VisitAgent[] = [
    { nume: detail.agent1_nume, perf: detail.agent1_perf, doi: detail.agent1_doi_pe_bon, focus: detail.agent1_focus, analiza: detail.agent1_analiza, plan: detail.agent1_plan },
    { nume: detail.agent2_nume, perf: detail.agent2_perf, doi: detail.agent2_doi_pe_bon, focus: detail.agent2_focus, analiza: detail.agent2_analiza, plan: detail.agent2_plan },
  ];
  return <div className="flex-1 space-y-4 p-4"><VisitPhotos detail={detail} photoIdx={photoIdx} onSelect={onPhotoSelect} /><VisitGeneral detail={detail} /><VisitCompliance detail={detail} /><VisitFinancial detail={detail} />{agents.filter((agent) => agent.nume).map((agent, index) => <AgentCard key={index} agent={agent} />)}{detail.notes && <div className="glass rounded-2xl p-4"><h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">Note</h4><p className="text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap">{detail.notes}</p></div>}</div>;
}

export function VisitDrawer({ visitId, onClose }: { visitId: string; onClose: () => void }) {
  const [photoIdx, setPhotoIdx] = useState(0);
  const drawerRef = useRef<HTMLDivElement>(null);
  const detailQuery = useQuery({ queryKey: queryKeys.visits.detail(visitId), queryFn: ({ signal }) => getVisitDetail(visitId, signal), staleTime: 5 * 60 * 1000 });
  const detail = detailQuery.data ?? null;
  useEffect(() => setPhotoIdx(0), [visitId]);
  useEffect(() => {
    const handler = (event: MouseEvent) => { if (drawerRef.current && !drawerRef.current.contains(event.target as Node)) onClose(); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"><div ref={drawerRef} className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-2xl dark:bg-slate-900">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"><div><p className="text-xs font-bold uppercase tracking-wide text-slate-400">Detalii Vizita</p>{detail && <p className="flex items-center text-sm font-bold text-slate-800 dark:text-slate-100"><FirmaBadge firma={detail.firma || ''} />{detail.magazin} · {detail.data_raport}</p>}</div><button onClick={onClose} className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Închide detaliile vizitei"><X size={18} /></button></div>
      {detailQuery.isPending && <div className="flex flex-1 items-center justify-center text-sm text-slate-400">Se incarca...</div>}
      {!detailQuery.isPending && detail && <VisitDetails detail={detail} photoIdx={photoIdx} onPhotoSelect={setPhotoIdx} />}
    </div></div>
  );
}
