// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const controller = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));
vi.mock('./useAgentEvaluationController', () => ({ useAgentEvaluationController: () => controller.current }));

import { AgentEvaluationSubtab } from './AgentEvaluationPage';
import {
  CompactSummary, FirmBadge, FirmSelector, formatMoney, formatNumber, formatPct, MechanismCard,
  MetricCell, MonthDropdown, MonthLabel, pointColor, scoreColor, StoreDropdown,
} from './AgentEvaluationControls';
import {
  AgentLegacyMobileCard, AgentRow, AgentV2MobileCard, AgentV2Row, componentWeights,
  ComponentScoreCell, flagLabel, getSortValue, getV2SortValue, referenceLabel, score100Color,
  SortHeader, targetSourceLabel, V2SortHeader,
} from './AgentEvaluationTables';
import { NewEvaluationSubsection } from './AgentEvaluationV2Table';

const legacy = {
  month: '2026-07', site_code: 'S1', agent: 'Ana', firma: 'Mobiup', locatie: 'Alfa', total_sales: 12000,
  working_days: 20, target_value: 10000, store_target: 20000, target_pct: 120, target_points: 3,
  daily_average: 600, daily_points: 2, value_reper: 101, value_reper_points: 3,
  bonuri_pct: 36, bonuri_points: 3, focus_pct: 8, focus_points: 2,
  premium_glass_pct: 50, premium_glass_qty: 5, glass_qty: 10, premium_glass_points: 3,
  total_points: 16, qualifier: 'Foarte bun',
};

const v2Base = {
  month: '2026-07', site_code: 'S1', agent: 'Ana', firma: 'Mobiup', locatie: 'Alfa', total_sales: 12000,
  working_days: 20, receipt_count: 50, total_score: 86, rating: 'Excelent', eligibility_status: 'eligibil',
  confidence_flags: ['luna_partiala', 'target_partial_din_grile', 'reper_istoric_locatie', 'extra_flag'],
  is_partial: false, period_month_count: 2, target_pct: 120, target_score: 25, target_source: 'agent_target',
  daily_vs_reference_pct: 116, daily_score: 20, daily_average: 600, daily_reference_type: 'colegi',
  bonuri_pct: 36, bonuri_score: 15, focus_pct: 10, focus_score: 15,
  premium_glass_pct: 50, premium_glass_score: 10, premium_glass_qty: 5, glass_qty: 10,
  value_reper: 101, value_reper_score: 15, trend_daily_pct: 12, trend_direction: 'up',
};

const v2Rows = [
  v2Base,
  { ...v2Base, month: '2026-08', site_code: 'S2', agent: 'Bogdan', firma: 'Mobicell', locatie: 'Beta', total_score: 60, rating: 'Risc', eligibility_status: 'eligibil', is_partial: true, period_month_count: 1, target_pct: null, target_score: 5, target_source: 'partial_agent_target', daily_reference_type: 'istoric_locatie', daily_score: 8, bonuri_score: 5, focus_score: 0, premium_glass_score: null, value_reper_score: 4, trend_daily_pct: -5, trend_direction: 'down', confidence_flags: ['reper_media_manager', 'folii_volum_mic'] },
  { ...v2Base, month: 'custom', site_code: 'S3', agent: 'Carmen', firma: 'Other', locatie: 'Gamma', total_score: null, rating: '-', eligibility_status: 'insuficient', target_score: 0, target_source: 'derived', daily_reference_type: 'none', daily_score: null, bonuri_score: 0, focus_score: 0, premium_glass_score: 0, value_reper_score: 0, trend_daily_pct: null, trend_direction: 'stable', confidence_flags: [], is_partial: false, period_month_count: 1 },
];

function model(overrides: Record<string, unknown> = {}) {
  return {
    mode: 'current', setMode: vi.fn(), selectedMonths: ['2026-07'], setSelectedMonths: vi.fn(), firma: '', setFirma: vi.fn(), asm: '', resetManager: vi.fn(), selectedStores: ['S1'], setSelectedStores: vi.fn(),
    sortKey: 'total_points', sortDirection: 'desc', v2SortKey: 'total_score', v2SortDirection: 'desc', loading: false,
    mobileFiltersOpen: true, setMobileFiltersOpen: vi.fn(), load: vi.fn(), toggleMonth: vi.fn(), toggleStore: vi.fn(),
    rows: [legacy], v2Rows, handleSort: vi.fn(), handleV2Sort: vi.fn(),
    summary: { agents: 1, avgPoints: 16, totalSales: 12000, premiumRows: 1 },
    optionData: { months: [{ value: '2026-07', label: 'Iulie' }, { value: '2026-06', label: 'Iunie' }], firmas: [{ value: 'Mobicell', label: 'Mobicell' }, { value: 'Other', label: 'Other' }, { value: 'Mobiup', label: 'Mobiup' }], asms: [{ value: 'RM A', label: 'RM A' }], stores: [{ value: 'S1', label: 'Alfa' }, { value: 'S2', label: 'Beta' }] },
    ...overrides,
  };
}

describe('agent evaluation critical surfaces', () => {
  beforeEach(() => { vi.clearAllMocks(); controller.current = model(); });

  it('covers formatting, colors, labels, weights and sorting edges', () => {
    expect(formatMoney(null)).toBe('-'); expect(formatMoney(10)).not.toBe('-');
    expect(formatPct(undefined)).toBe('-'); expect(formatPct(10)).toBe('10.0%');
    expect(formatNumber(null)).toBe('-'); expect(formatNumber(10.25, 1)).toBeTruthy();
    expect(scoreColor(16)).toContain('green'); expect(scoreColor(10)).toContain('amber'); expect(scoreColor(9)).toContain('red');
    expect(pointColor(3)).toContain('green'); expect(pointColor(1)).toContain('amber'); expect(pointColor(0)).toContain('red');
    expect(score100Color(80)).toContain('green'); expect(score100Color(60)).toContain('amber'); expect(score100Color(30)).toContain('red'); expect(score100Color(null)).toContain('slate'); expect(score100Color(90, 'insuficient')).toContain('slate');
    expect(componentWeights(v2Rows[1] as never).target).toBe(10); expect(componentWeights(v2Rows[0] as never).target).toBe(25);
    expect(flagLabel('luna_partiala')).toBe('lună parțială'); expect(flagLabel('new_flag')).toBe('new flag');
    expect(referenceLabel('colegi')).toBe('colegi'); expect(referenceLabel('istoric_locatie')).toBe('locație'); expect(referenceLabel('media_manager')).toBe('manager'); expect(referenceLabel('none')).toBe('fără reper');
    expect(targetSourceLabel('agent_target')).toBe('target agent'); expect(targetSourceLabel('partial_agent_target')).toBe('target mixt'); expect(targetSourceLabel('other')).toBe('target pe zile');
    expect(getSortValue(legacy as never, 'agent')).toContain('ana'); expect(getSortValue({ ...legacy, target_pct: null } as never, 'target_pct')).toBe(Number.NEGATIVE_INFINITY); expect(getSortValue({ ...legacy, target_pct: 'bad' } as never, 'target_pct')).toBe(Number.NEGATIVE_INFINITY); expect(getSortValue(legacy as never, 'month')).toBe('2026-07');
    expect(getV2SortValue(v2Rows[0] as never, 'agent')).toContain('ana'); expect(getV2SortValue(v2Rows[1] as never, 'target_pct')).toBe(Number.NEGATIVE_INFINITY); expect(getV2SortValue({ ...v2Base, total_score: 'bad' } as never, 'total_score')).toBe(Number.NEGATIVE_INFINITY); expect(getV2SortValue(v2Rows[0] as never, 'eligibility_status')).toBe('eligibil');
  });

  it('renders controls and executes dropdown/toggle branches', () => {
    const toggle = vi.fn(); const clear = vi.fn(); const firm = vi.fn();
    render(<><MonthLabel month="custom" /><MonthLabel month="2026-01..2026-03" /><MonthLabel month="bad.." /><MetricCell value={100} points={3} suffix="lei" /><MetricCell value={null} points={0} /><FirmBadge firma="Mobiup" /><FirmBadge firma="Mobicell" size="md" /><FirmBadge firma="Other" /><CompactSummary rows={[legacy] as never[]} summary={{ agents: 1, avgPoints: 16, totalSales: 12000, premiumRows: 1 }}>extra</CompactSummary><MechanismCard /><MonthDropdown months={model().optionData.months as never[]} selectedMonths={['2026-07']} onToggle={toggle} onClear={clear} /><FirmSelector options={model().optionData.firmas as never[]} selected="Mobiup" onChange={firm} /><StoreDropdown stores={model().optionData.stores as never[]} selectedStores={['S1']} onToggle={toggle} onClear={clear} /></>);
    fireEvent.click(screen.getByRole('button', { name: /Alocare puncte/ }));
    expect(screen.getByText(/3p >=100%/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Iulie 2026/ }));
    fireEvent.click(screen.getAllByRole('checkbox')[0]!);
    fireEvent.click(screen.getByRole('button', { name: 'Toate lunile' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mobiup' }));
    fireEvent.click(screen.getByRole('button', { name: /1 magazine/ }));
    fireEvent.click(screen.getAllByRole('checkbox').at(-1)!);
    fireEvent.click(screen.getByRole('button', { name: 'Toate magazinele' }));
    expect(toggle).toHaveBeenCalled(); expect(clear).toHaveBeenCalled(); expect(firm).toHaveBeenCalledWith('');
  });

  it('renders legacy and V2 rows/cards/cells and sorting callbacks', () => {
    const sort = vi.fn();
    render(<table><tbody><AgentRow row={legacy as never} /><AgentV2Row row={v2Rows[0] as never} /><AgentV2Row row={v2Rows[1] as never} /><AgentV2Row row={v2Rows[2] as never} /><tr><ComponentScoreCell value={1} score={null} weight={10} /><ComponentScoreCell value={1} score={8} weight={10} /><ComponentScoreCell value={1} score={2} weight={10} /><ComponentScoreCell value={1} score={0} weight={10} /></tr></tbody><thead><tr><SortHeader label="Agent sort" sortKey="agent" currentKey="agent" direction="asc" onSort={sort} /><V2SortHeader label="Score sort" sortKey="total_score" currentKey="agent" direction="desc" onSort={sort} /></tr></thead></table>);
    fireEvent.click(screen.getByRole('button', { name: 'Agent sort' })); fireEvent.click(screen.getByRole('button', { name: 'Score sort' }));
    expect(sort).toHaveBeenCalledWith('agent'); expect(sort).toHaveBeenCalledWith('total_score');
    const { rerender } = render(<><AgentLegacyMobileCard row={legacy as never} /><AgentV2MobileCard row={v2Rows[0] as never} /><AgentV2MobileCard row={v2Rows[2] as never} /></>);
    rerender(<AgentV2MobileCard row={{ ...v2Base, confidence_flags: [] } as never} />);
  });

  it('renders new subsection rich/empty and opens mechanism', () => {
    const onSort = vi.fn();
    const { rerender } = render(<NewEvaluationSubsection rows={v2Rows as never[]} sortKey="total_score" sortDirection="desc" onSort={onSort} />);
    fireEvent.click(screen.getByRole('button', { name: /Cum se face evaluarea/ }));
    expect(screen.getByText('Regula generala')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Agent' })[0]!);
    rerender(<NewEvaluationSubsection rows={[]} sortKey="agent" sortDirection="asc" onSort={onSort} />);
    expect(screen.getAllByText('Fără agenți pentru filtrele selectate.')).toHaveLength(2);
  });

  it('composes page current/new/mobile states and executes filters', () => {
    const { rerender } = render(<AgentEvaluationSubtab currentMonth="2026-08" months={['2026-07']} />);
    expect(screen.getByText('Mecanism analiză agenți')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reîncarcă analiza' }));
    fireEvent.click(screen.getByRole('button', { name: 'Închide' }));
    expect((controller.current.load as ReturnType<typeof vi.fn>)).toHaveBeenCalled();
    controller.current = model({ mode: 'new', mobileFiltersOpen: false, optionData: model().optionData });
    rerender(<AgentEvaluationSubtab currentMonth="2026-08" months={['2026-07']} />);
    expect(screen.getByText('Cum se face evaluarea')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Analiză' })[0]!);
    fireEvent.click(screen.getByRole('button', { name: 'Filtre' }));
  });
});
