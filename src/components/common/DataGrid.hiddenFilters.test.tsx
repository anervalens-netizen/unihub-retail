// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DataGridFilters } from '../../lib/dataGrid';
import { DataGrid, type DataGridColumn } from './DataGrid';
import { DataGridHiddenFilters } from './DataGridControls';

vi.mock('../ExportTableButton', () => ({
  ExportTableButton: ({ rows }: { rows: { id: string }[] }) => (
    <output data-testid="export-rows">{rows.map((row) => row.id).join(',')}</output>
  ),
}));

type Key = 'name' | 'city' | 'region' | 'sales';
interface Row { id: string; name: string; city: string; region: string; sales: number }
const rows: Row[] = [
  { id: 'a', name: 'Ana', city: 'Centru', region: 'N', sales: 100 },
  { id: 'b', name: 'Ana', city: 'Mall', region: 'N', sales: 200 },
  { id: 'c', name: 'Ana', city: 'Sud', region: 'S', sales: 250 },
  { id: 'd', name: 'Mihai', city: 'Mall', region: 'N', sales: 300 },
];
const columns: DataGridColumn<Row, Key>[] = [
  { key: 'name', label: 'Nume', value: (row) => row.name, render: (row) => row.name, hideable: false },
  { key: 'city', label: 'Magazin', value: (row) => row.city, render: (row) => row.city, filter: { kind: 'text' } },
  { key: 'region', label: 'Regiune', value: (row) => row.region, render: (row) => row.region,
    filter: { kind: 'enum', options: [{ value: 'N', label: 'Nord' }, { value: 'S', label: 'Sud' }] } },
  { key: 'sales', label: 'Vânzări', value: (row) => row.sales, render: (row) => row.sales, filter: { kind: 'number' } },
];
const groupName = 'Filtre pe coloane ascunse';

function renderGrid() {
  return render(
    <DataGrid title="Regional" rows={rows} columns={columns}
      initialSort={[{ key: 'sales', direction: 'desc' }]} rowKey={(row) => row.id}
      exportFilename="regional" exportSheetName="Regional" />,
  );
}

const cases: Array<{ label: string; filters: DataGridFilters<Key> }> = [
  { label: 'Magazin: <img src=x>', filters: { city: { kind: 'text', value: '<img src=x>' } } },
  { label: 'Regiune: Nord', filters: { region: { kind: 'enum', value: 'N' } } },
  { label: 'Regiune: Vest', filters: { region: { kind: 'enum', value: 'Vest' } } },
  { label: 'Vânzări: 0 – 250.5', filters: { sales: { kind: 'number', min: 0, max: 250.5 } } },
  { label: 'Vânzări: ≥ 0', filters: { sales: { kind: 'number', min: 0, max: null } } },
  { label: 'Vânzări: ≤ 200', filters: { sales: { kind: 'number', min: null, max: 200 } } },
  { label: 'Vânzări: ≤ 200', filters: { sales: { kind: 'number', min: NaN, max: 200 } } },
];

describe('DataGrid hidden-column filters', () => {
  it.each(cases)('describes $label without HTML interpretation', ({ label, filters }) => {
    const onClear = vi.fn();
    render(<DataGridHiddenFilters columns={columns} hidden={['city', 'region', 'sales']}
      filters={filters} tableId="grid" onClear={onClear} />);
    const button = within(screen.getByRole('group', { name: groupName }))
      .getByRole('button', { name: `Șterge filtrul ${label}` });
    expect(button).toHaveTextContent(label);
    expect(button).toHaveAttribute('aria-controls', 'grid');
    expect(button.querySelector('img')).toBeNull();
    fireEvent.click(button);
    expect(onClear).toHaveBeenCalledExactlyOnceWith(Object.keys(filters)[0]);
  });

  it('does not add a summary for visible or inactive filters', () => {
    render(<DataGridHiddenFilters columns={columns} hidden={['city', 'sales']}
      filters={{ city: { kind: 'text', value: '  ' }, sales: { kind: 'number', min: null, max: Infinity },
        region: { kind: 'enum', value: 'N' } }} tableId="grid" onClear={vi.fn()} />);
    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
  });

  it('clears only the hidden range, preserving search, other filters, sort and export', () => {
    renderGrid();
    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
    const search = screen.getByRole('searchbox', { name: 'Caută în coloanele afișate din Regional' });
    fireEvent.change(search, { target: { value: 'ana' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minim Vânzări' }), { target: { value: '150' } });
    expect(screen.getByTestId('export-rows')).toHaveTextContent(/^b$/);

    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Vânzări' }));
    expect(screen.queryByTestId('data-grid-header-sales')).not.toBeInTheDocument();
    expect(screen.getByTestId('export-rows')).toHaveTextContent(/^b$/);
    fireEvent.click(screen.getByRole('button', { name: 'Șterge filtrul Vânzări: ≥ 150' }));

    expect(search).toHaveValue('ana');
    expect(screen.getByRole('combobox', { name: 'Filtrează Regiune' })).toHaveValue('N');
    expect(screen.getByRole('button', { name: 'Șterge filtrele (2)' })).toBeInTheDocument();
    expect(screen.getByTestId('export-rows')).toHaveTextContent(/^b,a$/);
    expect(screen.queryByTestId('data-grid-header-sales')).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
  });

  it('retains filters on show/hide and lets clear-all remove every summary', () => {
    renderGrid();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Filtrează Magazin' }), { target: { value: 'Mall' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Magazin' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    const group = screen.getByRole('group', { name: groupName });
    expect(within(group).getAllByRole('button')).toHaveLength(2);
    expect(screen.getByTestId('export-rows')).toHaveTextContent(/^d,b$/);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Magazin' }));
    expect(screen.getByRole('searchbox', { name: 'Filtrează Magazin' })).toHaveValue('Mall');
    expect(screen.queryByRole('button', { name: 'Șterge filtrul Magazin: Mall' })).not.toBeInTheDocument();
    expect(within(group).getAllByRole('button')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Șterge filtrele (2)' }));
    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
    expect(screen.getByTestId('export-rows')).toHaveTextContent(/^d,c,b,a$/);
    expect(screen.queryByTestId('data-grid-header-region')).not.toBeInTheDocument();
  });

  it('moves keyboard focus to the next remaining hidden chip when a middle chip is removed', () => {
    renderGrid();
    // Set up three hidden filters (city, region, sales) by hiding those columns.
    fireEvent.change(screen.getByRole('searchbox', { name: 'Filtrează Magazin' }), { target: { value: 'Mall' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minim Vânzări' }), { target: { value: '150' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Magazin' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Vânzări' }));
    fireEvent.click(screen.getByText('Coloane', { exact: true }));

    const group = screen.getByRole('group', { name: groupName });
    expect(within(group).getAllByRole('button')).toHaveLength(3);

    const regionChip = within(group).getByRole('button', { name: 'Șterge filtrul Regiune: Nord' });
    regionChip.focus();
    fireEvent.click(regionChip);

    const salesChip = within(group).getByRole('button', { name: 'Șterge filtrul Vânzări: ≥ 150' });
    expect(salesChip).toHaveFocus();
  });

  it('falls back to the previous chip when the removed chip is the last remaining one', () => {
    renderGrid();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Filtrează Magazin' }), { target: { value: 'Mall' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Magazin' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    fireEvent.click(screen.getByText('Coloane', { exact: true }));

    const group = screen.getByRole('group', { name: groupName });
    const regionChip = within(group).getByRole('button', { name: 'Șterge filtrul Regiune: Nord' });
    regionChip.focus();
    fireEvent.click(regionChip);

    const cityChip = within(group).getByRole('button', { name: 'Șterge filtrul Magazin: Mall' });
    expect(cityChip).toHaveFocus();
  });

  it('moves focus to the clear-all button when the last hidden chip is removed and other filters remain', () => {
    renderGrid();
    // Keep the global search active so the clear-all button stays visible
    // after the hidden chip is the last column filter to be removed.
    fireEvent.change(screen.getByRole('searchbox', { name: 'Caută în coloanele afișate din Regional' }), { target: { value: 'ana' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    fireEvent.click(screen.getByText('Coloane', { exact: true }));

    const chip = screen.getByRole('button', { name: 'Șterge filtrul Regiune: Nord' });
    chip.focus();
    fireEvent.click(chip);

    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Șterge filtrele (1)' })).toHaveFocus();
  });

  it('falls back to the global search input when no chips and no clear-all remain', () => {
    renderGrid();
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), { target: { value: 'N' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));

    const chip = screen.getByRole('button', { name: 'Șterge filtrul Regiune: Nord' });
    chip.focus();
    fireEvent.click(chip);

    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Șterge filtrele (1)' })).not.toBeInTheDocument();
    const search = screen.getByRole('searchbox', { name: 'Caută în coloanele afișate din Regional' });
    expect(search).toHaveFocus();
  });

  it('does not steal focus when an unrelated control clears a filter', () => {
    renderGrid();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Filtrează Magazin' }), { target: { value: 'Mall' } });
    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Magazin' }));
    fireEvent.click(screen.getByText('Coloane', { exact: true }));

    // Focus a stable visible control (the global search input) so we can
    // verify that clearing the filter via the toolbar does not steal it.
    const other = screen.getByRole('searchbox', { name: 'Caută în coloanele afișate din Regional' });
    other.focus();
    expect(other).toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: 'Șterge filtrele (1)' }));

    expect(screen.queryByRole('group', { name: groupName })).not.toBeInTheDocument();
    expect(other).toHaveFocus();
  });
});
