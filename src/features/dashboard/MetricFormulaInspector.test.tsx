// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { getMetricDefinition } from '../../lib/metricCatalog';
import { MetricFormulaInspector } from './MetricFormulaInspector';

const context = {
  period: '2026-09',
  filters: {
    firma: 'Mobiup',
    rm: 'Nord',
    magazin: ['S1'],
    agent: ['Ana'],
  },
  statusLabel: 'Luna in curs 2026-09 este inca in actualizare pana in ziua 10 din 30.',
  lastSaleDate: '2026-09-10',
  importedDayOfMonth: 10,
  daysInMonth: 30,
};

describe('MetricFormulaInspector', () => {
  it.each([
    ['retail.receipts.bon2acc_pct' as const, 40, 'Bon2Acc'],
    ['retail.focus.accessory_pct' as const, 30, 'Focus / accesorii'],
  ])('uses Metric Catalog metadata for %s in the active Dashboard context', (metricId, value, metricName) => {
    const metric = getMetricDefinition(metricId);
    render(<MetricFormulaInspector metricId={metricId} value={value} context={context} />);

    const inspector = screen.getByTestId(`formula-inspector-${metricId}`);
    fireEvent.click(within(inspector).getByLabelText(`Inspectează formula ${metricName}`));

    expect(within(inspector).getByText(`${value.toFixed(2)}%`)).toBeInTheDocument();
    expect(within(inspector).getByText('2026-09')).toBeInTheDocument();
    expect(within(inspector).getByText('2026-09-10')).toBeInTheDocument();
    expect(within(inspector).getByText('Acoperire vânzări în scope')).toBeInTheDocument();
    expect(within(inspector).getByText('Până la ziua 10 din 30')).toBeInTheDocument();
    expect(within(inspector).queryByText('Import lunar')).not.toBeInTheDocument();
    expect(within(inspector).getByText('Firma')).toBeInTheDocument();
    expect(within(inspector).getByText('Manager')).toBeInTheDocument();
    expect(within(inspector).getByText('Magazin')).toBeInTheDocument();
    expect(within(inspector).getByText('Agent')).toBeInTheDocument();
    expect(within(inspector).getAllByText('Suprascris de Magazin')).toHaveLength(2);
    expect(within(inspector).queryByText('Mobiup')).not.toBeInTheDocument();
    expect(within(inspector).queryByText('Nord')).not.toBeInTheDocument();
    expect(within(inspector).getByText('S1')).toBeInTheDocument();
    expect(within(inspector).getByText('Ana')).toBeInTheDocument();
    expect(within(inspector).getByText(metric!.formula)).toBeInTheDocument();
    expect(within(inspector).getByText(metric!.sources[0]!)).toBeInTheDocument();
    expect(within(inspector).getByText(metric!.freshness)).toBeInTheDocument();
    expect(within(inspector).getByText(/Catalog KPI v1 · read-only/)).toBeInTheDocument();
  });

  it('shows canonical hierarchy labels when store scope is not selected', () => {
    render(
      <MetricFormulaInspector
        metricId="retail.receipts.bon2acc_pct"
        value={40}
        context={{
          ...context,
          filters: { ...context.filters, magazin: [] },
        }}
      />,
    );

    const inspector = screen.getByTestId('formula-inspector-retail.receipts.bon2acc_pct');
    fireEvent.click(within(inspector).getByLabelText('Inspectează formula Bon2Acc'));

    expect(within(inspector).getByText('Mobiup')).toBeInTheDocument();
    expect(within(inspector).getByText('Nord')).toBeInTheDocument();
    expect(within(inspector).getByText('Toate magazinele din scope')).toBeInTheDocument();
  });

  it('mirrors API sentinel normalization before deriving displayed filter scope', () => {
    render(
      <MetricFormulaInspector
        metricId="retail.receipts.bon2acc_pct"
        value={40}
        context={{
          ...context,
          filters: {
            firma: 'Mobiup',
            rm: 'Nord',
            magazin: ['Toate', 'tOtI', 'Toți', 'ToÈ›I', 'ToÃˆâ€ºI', '   '],
            agent: ['Toti'],
          },
        }}
      />,
    );

    const inspector = screen.getByTestId('formula-inspector-retail.receipts.bon2acc_pct');
    fireEvent.click(within(inspector).getByLabelText('Inspectează formula Bon2Acc'));

    expect(within(inspector).getByText('Mobiup')).toBeInTheDocument();
    expect(within(inspector).getByText('Nord')).toBeInTheDocument();
    expect(within(inspector).getByText('Toate magazinele din scope')).toBeInTheDocument();
    expect(within(inspector).getByText('Toți agenții din scope')).toBeInTheDocument();
    expect(within(inspector).queryByText('Suprascris de Magazin')).not.toBeInTheDocument();
  });

  it('normalizes scalar hierarchy sentinels like the API boundary', () => {
    render(
      <MetricFormulaInspector
        metricId="retail.receipts.bon2acc_pct"
        value={40}
        context={{
          ...context,
          filters: { firma: 'TOATE', rm: 'toți', magazin: [], agent: [] },
        }}
      />,
    );

    const inspector = screen.getByTestId('formula-inspector-retail.receipts.bon2acc_pct');
    fireEvent.click(within(inspector).getByLabelText('Inspectează formula Bon2Acc'));

    expect(within(inspector).getByText('Toate firmele')).toBeInTheDocument();
    expect(within(inspector).getByText('Toți managerii')).toBeInTheDocument();
  });

  it('states unavailable scoped coverage instead of inventing data', () => {
    render(
      <MetricFormulaInspector
        metricId="retail.receipts.bon2acc_pct"
        value={null}
        context={{
          ...context,
          lastSaleDate: null,
          importedDayOfMonth: null,
          daysInMonth: null,
        }}
      />,
    );

    const inspector = screen.getByTestId('formula-inspector-retail.receipts.bon2acc_pct');
    fireEvent.click(within(inspector).getByLabelText('Inspectează formula Bon2Acc'));

    expect(within(inspector).getByText('Indisponibil')).toBeInTheDocument();
    expect(within(inspector).getByText('Indisponibilă')).toBeInTheDocument();
    expect(within(inspector).getByText('Indisponibil în răspunsul curent')).toBeInTheDocument();
  });
});
