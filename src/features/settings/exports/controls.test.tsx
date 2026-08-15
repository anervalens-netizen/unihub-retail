// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { vi } from 'vitest';

import { CheckRow, ColumnBlock, ExportWorkflow, FieldBlock, FilterBlock, LevelBlock, ModeButton, PeriodSelector } from './controls';
import { ErpReconciliationResult } from '../imports/ErpReconciliationResult';

describe('Settings export controls', () => {
  it('exposes the active export step in the DOM', () => {
    render(<ExportWorkflow step={4} onChange={() => undefined} />);

    expect(screen.getByRole('navigation', { name: 'Pași export Excel' })).toBeInTheDocument();
    expect(screen.getByText('Pasul 4 din 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { current: 'step' })).toHaveTextContent('Preview și export');
  });

  it('renders period controls with the selected-day summary', () => {
    render(
      <PeriodSelector
        years={['2026']}
        selectedYears={['2026']}
        onYearToggle={() => undefined}
        monthNumbers={['08']}
        selectedMonthNumbers={['08']}
        onMonthToggle={() => undefined}
        selectedDays={[1, 2]}
        onDayToggle={() => undefined}
        onSelectAllDays={() => undefined}
        onSelectFirstNineDays={() => undefined}
        selectedMonthCount={1}
      />,
    );

    expect(screen.getByText('1 luni rezultate · zilele 1, 2')).toBeInTheDocument();
    expect(screen.getAllByText('August')).toHaveLength(2);
  });

  it('executes workflow, period and reusable filter controls across their branches', () => {
    const changeStep = vi.fn(); const toggle = vi.fn(); const click = vi.fn();
    render(<>
      <ExportWorkflow step={2} onChange={changeStep} />
      <PeriodSelector years={['2026']} selectedYears={[]} onYearToggle={toggle} monthNumbers={['01', '99']} selectedMonthNumbers={['01', '02', '99']} onMonthToggle={toggle} selectedDays={Array.from({ length: 31 }, (_, index) => index + 1)} onDayToggle={toggle} onSelectAllDays={click} onSelectFirstNineDays={click} selectedMonthCount={3} />
      <ModeButton active icon={<span>!</span>} title="Activ" subtitle="detaliu" onClick={click} />
      <ModeButton active={false} icon={<span>?</span>} title="Inactiv" subtitle="detaliu" onClick={click} />
      <FieldBlock title="Camp"><span>valoare</span></FieldBlock>
      <ColumnBlock title="Coloane" columns={[{ key: 'one', label: 'Prima', group: 'base' } as never, { key: 'two', label: 'A doua', group: 'base' } as never]} selected={['one', 'missing']} onToggle={toggle} />
      <LevelBlock levels={[{ key: 'store', label: 'Magazin' }]} selected={['store']} onToggle={toggle} />
      <FilterBlock title="Filtru" values={['Alfa', { key: 'beta', label: 'Beta' }]} selected={['Alfa']} onToggle={toggle} />
      <CheckRow label="Direct" checked onChange={toggle} />
    </>);
    fireEvent.click(screen.getByRole('button', { name: /Dataset/ }));
    fireEvent.click(screen.getByText('2026').closest('label')!.querySelector('input')!);
    fireEvent.click(screen.getByRole('button', { name: 'Toate' }));
    fireEvent.click(screen.getByRole('button', { name: 'Primele 9' }));
    fireEvent.click(screen.getByRole('button', { name: /Activ/ }));
    fireEvent.click(screen.getByText('Prima').closest('label')!.querySelector('input')!);
    fireEvent.click(screen.getByText('Magazin').closest('label')!.querySelector('input')!);
    fireEvent.change(screen.getByPlaceholderText('Cauta...'), { target: { value: 'bet' } });
    fireEvent.click(screen.getByText('Beta').closest('label')!.querySelector('input')!);
    expect(screen.getByText('3 luni rezultate · toate zilele')).toBeInTheDocument();
    expect(toggle).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(changeStep).toHaveBeenCalledWith(1);
  });

  it('renders ERP reconciliation differences and matching outcomes', () => {
    const difference = {
      status: 'differences', issue_count: 3, omitted_issue_count: 2, import_month: '2026-08', report_cutoff_date: '2026-08-09', retail_cutoff_date: '2026-08-08', file_digest: 'sha256:test', report_store_count: 2, retail_store_count: 3, report_agent_count: 4, retail_agent_count: 5,
      metrics: [
        { key: 'sales', label: 'Vanzari', status: 'difference', report_value: 100, retail_value: 90, unit: 'currency', note: 'dif' },
        { key: 'qty', label: 'Cantitate', status: 'explained', report_value: 10, retail_value: 9, unit: 'integer', note: null },
        { key: 'stores', label: 'Magazine', status: 'match', report_value: 2, retail_value: 2, unit: 'integer', note: null },
      ],
      issues: [
        { scope: 'agent', site_code: 'S1', entity: 'A', metric: 'sales', report_value: 10, retail_value: 9, difference: 1, note: 'agent' },
        { scope: 'store', site_code: null, entity: 'S', metric: 'qty', report_value: 2, retail_value: 1, difference: 1, note: 'store' },
        { scope: 'report', site_code: 'S2', entity: 'R', metric: 'total', report_value: 3, retail_value: 1, difference: 2, note: 'report' },
      ],
      app_only_metrics: [{ key: 'promo', label: 'Promo', value: 5, unit: 'integer', note: 'doar Retail' }], notes: ['Nota'],
    };
    const { rerender } = render(<ErpReconciliationResult result={difference as never} />);
    expect(screen.getByText(/3 diferențe de detaliu/)).toBeInTheDocument();
    expect(screen.getByText(/Încă 2 diferențe/)).toBeInTheDocument();
    expect(screen.getByText('Agent')).toBeInTheDocument();
    expect(screen.getByText('Magazin')).toBeInTheDocument();
    expect(screen.getByText('Raport')).toBeInTheDocument();
    rerender(<ErpReconciliationResult result={{ ...difference, status: 'match', issue_count: 0, omitted_issue_count: 0, retail_cutoff_date: null, metrics: [], issues: [], app_only_metrics: [], notes: [] } as never} />);
    expect(screen.getByText('Raportul coincide cu datele verificabile din Retail')).toBeInTheDocument();
    rerender(<ErpReconciliationResult result={{ ...difference, issue_count: 0, issues: [] } as never} />);
    expect(screen.getByText('Au fost găsite diferențe în totalurile comparate')).toBeInTheDocument();
  });
});
