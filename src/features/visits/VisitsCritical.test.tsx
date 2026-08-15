// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ report: vi.fn(), tree: vi.fn(), detail: vi.fn(), photo: vi.fn(), filters: vi.fn() }));
vi.mock('../../api/visitsReport', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../api/visitsReport')>()), getVisitsReport: api.report, getVisitsTree: api.tree, getVisitDetail: api.detail, getVisitPhoto: api.photo }));
vi.mock('../../api/filters', () => ({ getFilterOptions: api.filters }));

import { VisiteSubtab } from '../../components/VisiteSubtab';
import { CompletionBadge, VisitDrawer } from './VisitDrawer';
import { MonthPicker, TeamLeaderRow } from './VisitsTree';

function wrapper(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const visit = { id: 'v1', magazin: 'S1', locatie: 'Alfa', firma: 'Mobiup', ora: '10:30:00', has_photos: true, completion_pct: 85 };
const group = { team_leader: 'Team Leader A', nr_vizite: 1, months: [{ month: '2026-08', nr_vizite: 1, days: [{ date: '2026-08-10', visits: [visit] }] }] };
const summary = { total_vizite: 1, magazine_unice: 1, avg_completion: 85, rows: [{ curatenie_pct: 90, imagine_pct: 70, uniforma_pct: 40, afise_pct: 100, produse_promo_pct: 50 }] };
const detail = {
  id: 'v1', magazin: 'Alfa', firma: 'Mobiup', data_raport: '2026-08-10', team_leader: 'Team Leader A', asm: 'RM A',
  durata_vizita_ore: 1.5, ora_trimitere: '10:30', completion_pct: 85, photos: ['one.jpg', 'two.jpg'],
  curatenie: true, imagine: false, uniforma: true, afise: false, produse_promo: true, avizat: false,
  tpu: 1, sticla: 2, altele: 3, charisma: 4, casa: 5, incarcari_epay: 6, incarcari_charisma: 7,
  agent1_nume: 'Ana', agent1_perf: 90, agent1_doi_pe_bon: 30, agent1_focus: 8, agent1_analiza: 'Bine', agent1_plan: 'Continuă',
  agent2_nume: 'Bogdan', agent2_perf: null, agent2_doi_pe_bon: null, agent2_focus: null, agent2_analiza: null, agent2_plan: null,
  notes: 'Notă vizită',
};

describe('visits critical surfaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.report.mockResolvedValue(summary); api.tree.mockResolvedValue({ team_leaders: [group] });
    api.detail.mockResolvedValue(detail); api.photo.mockResolvedValue(new Blob(['photo']));
    api.filters.mockResolvedValue({ firme: [], regionali: [], asmi: [], magazine: [{ site_code: 'S1' }, { site_code: 'S2' }], agenti: [] });
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  });

  it('loads the month, filters team leaders and opens a rich visit drawer', async () => {
    render(wrapper(<VisiteSubtab currentMonth="2026-08" months={['2026-07', '2026-08', '2026-08']} />));
    expect(await screen.findByText('Vizite pe Team Leader')).toBeInTheDocument();
    expect(screen.getAllByText('50%')).toHaveLength(2);
    fireEvent.change(screen.getByPlaceholderText('Caută Team Leader'), { target: { value: 'Team Leader' } });
    fireEvent.click(screen.getByRole('button', { name: /Team Leader A/ }));
    fireEvent.click(screen.getByRole('button', { name: /Alfa/ }));
    fireEvent.click(screen.getByRole('button', { name: /10 aug\..*85%/ }));
    expect(screen.getByText('Detalii Vizita')).toBeInTheDocument();
    expect(await screen.findByText('Financiar')).toBeInTheDocument();
    expect(screen.getByText('Agent — Ana')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /thumb 2/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Închide detaliile vizitei' }));
  });

  it('covers direct tree/month/badge branches and empty month picker', () => {
    const open = vi.fn(); const change = vi.fn();
    const { rerender } = render(<><CompletionBadge pct={90} /><CompletionBadge pct={60} /><CompletionBadge pct={20} /><MonthPicker months={['2026-08']} selected="2026-08" onChange={change} /><TeamLeaderRow group={{ ...group, months: [{ month: '2026-08', nr_vizite: 2, days: [{ date: '—', visits: [{ ...visit, id: 'v2', magazin: '', locatie: null, firma: null, ora: null, has_photos: false, completion_pct: 40 }, visit] }] }] } as never} onOpenVisit={open} /></>);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-08' } });
    fireEvent.click(screen.getByRole('button', { name: /Team Leader A/ }));
    fireEvent.click(screen.getByRole('button', { name: /Alfa.*viz\./ }));
    fireEvent.click(screen.getByRole('button', { name: /10:30.*85%/ }));
    expect(open).toHaveBeenCalled();
    rerender(<MonthPicker months={[]} selected="" onChange={change} />);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('covers loading/error/no-month/empty-group/no-universe states', async () => {
    let resolveReport!: (value: unknown) => void; let resolveTree!: (value: unknown) => void;
    api.report.mockReturnValueOnce(new Promise((resolve) => { resolveReport = resolve; }));
    api.tree.mockReturnValueOnce(new Promise((resolve) => { resolveTree = resolve; }));
    const { rerender } = render(wrapper(<VisiteSubtab currentMonth="2026-08" months={['2026-08']} />));
    expect(screen.getByText('Se incarca vizitele...')).toBeInTheDocument();
    resolveReport(summary); resolveTree({ team_leaders: [] });
    await waitFor(() => expect(api.report).toHaveBeenCalled());

    api.report.mockRejectedValueOnce(new Error('offline')); api.tree.mockResolvedValueOnce({ team_leaders: [] });
    rerender(wrapper(<VisiteSubtab key="error" currentMonth="2026-07" months={['2026-07']} />));
    expect(await screen.findByText('offline')).toBeInTheDocument();

    rerender(wrapper(<VisiteSubtab key="none" currentMonth="" months={[]} />));
    expect(await screen.findByText('Nicio vizita inregistrata')).toBeInTheDocument();

    api.report.mockResolvedValueOnce({ ...summary, rows: [], avg_completion: 40, magazine_unice: 0 }); api.tree.mockResolvedValueOnce({ team_leaders: [] }); api.filters.mockResolvedValueOnce({ magazine: [] });
    rerender(wrapper(<VisiteSubtab key="empty" currentMonth="2026-06" months={['2026-06']} />));
    expect(await screen.findByText('Nicio vizita pentru luna selectata')).toBeInTheDocument();
    expect(screen.getByText('univers indisponibil')).toBeInTheDocument();
  });

  it('covers drawer empty financial/photos and outside-close paths', async () => {
    api.detail.mockResolvedValueOnce({ ...detail, photos: [], tpu: null, sticla: null, altele: null, charisma: null, casa: null, incarcari_epay: null, incarcari_charisma: null, agent1_nume: null, agent2_nume: null, notes: null, asm: null, ora_trimitere: null });
    const close = vi.fn();
    render(wrapper(<VisitDrawer visitId="v2" onClose={close} />));
    expect(await screen.findByText('General')).toBeInTheDocument();
    expect(screen.queryByText('Financiar')).not.toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(close).toHaveBeenCalled();
  });
});
