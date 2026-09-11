// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MetricCatalogView } from './MetricCatalogView';

describe('MetricCatalogView', () => {
  it('renders the bounded catalog and exposes real threshold metadata', () => {
    render(<MetricCatalogView />);

    expect(screen.getByRole('heading', { name: 'Catalog KPI' })).toBeInTheDocument();
    expect(screen.getByText('v1 · 11 metrici')).toBeInTheDocument();
    expect(screen.getAllByTestId('metric-catalog-card')).toHaveLength(11);

    const bon2Card = screen.getByText('Bon2Acc').closest('article');
    expect(bon2Card).not.toBeNull();
    expect(within(bon2Card as HTMLElement).getByText('Critic')).toBeInTheDocument();
    expect(within(bon2Card as HTMLElement).getByText('< 28%')).toBeInTheDocument();
    expect(within(bon2Card as HTMLElement).getByText('Foarte bun')).toBeInTheDocument();
    expect(within(bon2Card as HTMLElement).getByText('≥ 31%')).toBeInTheDocument();
  });

  it('filters by id/source semantics and reports an empty search honestly', () => {
    render(<MetricCatalogView />);
    const search = screen.getByRole('searchbox', { name: 'Caută în Catalog KPI' });

    fireEvent.change(search, { target: { value: 'return_receipt_count' } });
    expect(screen.getAllByTestId('metric-catalog-card')).toHaveLength(1);
    expect(screen.getByText('Bonuri retur')).toBeInTheDocument();
    expect(screen.getByText('1 din 11 metrici')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'nu-exista-metrica' } });
    expect(screen.queryAllByTestId('metric-catalog-card')).toHaveLength(0);
    expect(screen.getByText('Nicio metrică nu corespunde căutării.')).toBeInTheDocument();
    expect(screen.getByText('0 din 11 metrici')).toBeInTheDocument();
  });

  it('keeps implementation details collapsed until explicitly requested', () => {
    render(<MetricCatalogView />);
    fireEvent.change(screen.getByRole('searchbox', { name: 'Caută în Catalog KPI' }), {
      target: { value: 'retail.sales.avg_receipt_value' },
    });

    const details = screen.getByText('Detalii tehnice').closest('details');
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute('open');
    fireEvent.click(screen.getByText('Detalii tehnice'));
    expect(details).toHaveAttribute('open');
    expect(screen.getByText('backend/services/dashboard/query_comparison.py::_fetch_comparison_point')).toBeInTheDocument();
  });
});
