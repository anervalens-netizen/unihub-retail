// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../ExportTableButton', () => ({
  ExportTableButton: ({
    rows,
    columns,
  }: {
    rows: unknown[];
    columns: Array<{ header: string }>;
  }) => (
    <output
      data-testid="export-probe"
      data-rows={rows.length}
      data-columns={columns.length}
      data-headers={columns.map((column) => column.header).join('|')}
    />
  ),
}));

import { DataGrid, type DataGridColumn } from './DataGrid';

type Key = 'name' | 'region' | 'sales';
interface Row {
  id: string;
  name: string;
  region: string;
  sales: number | null;
}

type Sort = { key: Key; direction: 'asc' | 'desc' };

const rows: Row[] = [
  { id: 'a', name: 'Ana', region: 'Sud', sales: 100 },
  { id: 'b', name: 'Ana', region: 'Nord', sales: 200 },
  { id: 'c', name: 'Ștefan', region: 'Sud', sales: 150 },
  { id: 'd', name: 'Mihai', region: 'Nord', sales: null },
];

const columns: DataGridColumn<Row, Key>[] = [
  {
    key: 'name',
    label: 'Nume',
    value: (row) => row.name,
    render: (row) => `${row.id}:${row.name}`,
    filter: { kind: 'text', placeholder: 'Caută nume' },
    defaultDirection: 'asc',
    hideable: false,
    exportValue: (row) => row.name,
  },
  {
    key: 'region',
    label: 'Regiune',
    value: (row) => row.region,
    render: (row) => row.region,
    filter: {
      kind: 'enum',
      allLabel: 'Toate regiunile',
      options: [
        { value: 'Nord', label: 'Nord' },
        { value: 'Sud', label: 'Sud' },
      ],
    },
    defaultDirection: 'asc',
  },
  {
    key: 'sales',
    label: 'Vânzări',
    value: (row) => row.sales,
    render: (row) => row.sales ?? '—',
    filter: { kind: 'number', step: 1 },
    exportFormat: 'currency',
  },
];

function renderGrid(
  data: Row[] = rows,
  onSortChange?: (sorts: readonly Sort[]) => void,
) {
  return render(
    <DataGrid
      title="Regional"
      subtitle="Pilot"
      rows={data}
      columns={columns}
      initialSort={[{ key: 'sales', direction: 'desc' }]}
      onSortChange={onSortChange}
      rowKey={(row) => row.id}
      exportFilename="regional"
      exportSheetName="Regional"
    />,
  );
}

function renderedNames(): string[] {
  return screen.queryAllByTestId('data-grid-row').map((row: HTMLElement) =>
    within(row).getAllByRole('cell')[0]?.textContent ?? '',
  );
}

describe('DataGrid', () => {
  it('keeps stable sorting, supports multi-sort and reports the full sort state', () => {
    const onSortChange = vi.fn<(sorts: readonly Sort[]) => void>();
    renderGrid(rows, onSortChange);

    expect(renderedNames()).toEqual(['b:Ana', 'c:Ștefan', 'a:Ana', 'd:Mihai']);
    expect(screen.getByTestId('data-grid-header-sales')).toHaveAttribute(
      'aria-sort',
      'descending',
    );
    const sortStatus = screen.getByRole('status');
    expect(sortStatus).toHaveTextContent('Sortare activă: 1. Vânzări, descrescător.');
    expect(screen.getByRole('button', { name: 'Sortează după Nume' })).toHaveAttribute(
      'aria-describedby',
      sortStatus.id,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Sortează după Nume' }));
    expect(renderedNames()).toEqual(['a:Ana', 'b:Ana', 'd:Mihai', 'c:Ștefan']);
    expect(onSortChange).toHaveBeenLastCalledWith([
      { key: 'name', direction: 'asc' },
    ]);

    fireEvent.click(
      screen.getByRole('button', { name: 'Sortează după Vânzări' }),
      { shiftKey: true },
    );
    expect(renderedNames()).toEqual(['b:Ana', 'a:Ana', 'd:Mihai', 'c:Ștefan']);
    expect(onSortChange).toHaveBeenLastCalledWith([
      { key: 'name', direction: 'asc' },
      { key: 'sales', direction: 'desc' },
    ]);
    expect(screen.getByTestId('data-grid-sort-priority-name')).toHaveTextContent('1');
    expect(screen.getByTestId('data-grid-sort-priority-sales')).toHaveTextContent('2');
    expect(screen.getByTestId('data-grid-header-name')).toHaveAttribute(
      'aria-sort',
      'ascending',
    );
    expect(screen.getByTestId('data-grid-header-sales')).not.toHaveAttribute('aria-sort');
    expect(sortStatus).toHaveTextContent(
      'Sortare activă: 1. Nume, crescător; 2. Vânzări, descrescător.',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Sortează după Nume' }));
    expect(renderedNames()).toEqual(['c:Ștefan', 'd:Mihai', 'a:Ana', 'b:Ana']);
    expect(onSortChange).toHaveBeenLastCalledWith([
      { key: 'name', direction: 'desc' },
    ]);
    expect(sortStatus).toHaveTextContent('Sortare activă: 1. Nume, descrescător.');
  });

  it('filters text, enum and numeric values and exports only the current view', () => {
    renderGrid();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Filtrează Nume' }), {
      target: { value: 'stef' },
    });
    expect(renderedNames()).toEqual(['c:Ștefan']);
    expect(screen.getByTestId('export-probe')).toHaveAttribute('data-rows', '1');
    expect(screen.getByText('1 din 4 înregistrări')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Șterge filtrele (1)' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Filtrează Regiune' }), {
      target: { value: 'Nord' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minim Vânzări' }), {
      target: { value: '150' },
    });
    expect(renderedNames()).toEqual(['b:Ana']);
    expect(screen.getByRole('button', { name: 'Șterge filtrele (2)' })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('spinbutton', { name: 'Maxim Vânzări' }), {
      target: { value: '180' },
    });
    expect(screen.getByText('Nu există rezultate pentru filtrele selectate.')).toBeInTheDocument();
    expect(screen.getByTestId('export-probe')).toHaveAttribute('data-rows', '0');
  });

  it('hides, reorders and resets columns while preserving one visible column', () => {
    renderGrid();
    const table = screen.getByRole('table', { name: 'Regional' });
    expect(table.closest('section')).not.toHaveClass('overflow-hidden');
    expect(table.parentElement).toHaveClass('overflow-auto');

    fireEvent.click(screen.getByText('Coloane'));

    expect(screen.getByRole('checkbox', { name: 'Afișează Nume' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    expect(screen.queryByTestId('data-grid-header-region')).not.toBeInTheDocument();
    expect(screen.getByTestId('export-probe')).toHaveAttribute('data-columns', '2');
    expect(screen.getByTestId('export-probe')).toHaveAttribute(
      'data-headers',
      'Nume|Vânzări',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mută Vânzări la stânga' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mută Vânzări la stânga' }));
    expect(screen.getAllByTestId(/^data-grid-header-/).map((header: HTMLElement) => header.dataset.testid))
      .toEqual(['data-grid-header-sales', 'data-grid-header-name']);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Vânzări' }));
    expect(screen.getAllByTestId(/^data-grid-header-/)).toHaveLength(1);
    expect(screen.getByTestId('export-probe')).toHaveAttribute('data-columns', '1');

    fireEvent.click(screen.getByRole('button', { name: 'Resetează coloanele' }));
    expect(screen.getAllByTestId(/^data-grid-header-/).map((header: HTMLElement) => header.dataset.testid))
      .toEqual([
        'data-grid-header-name',
        'data-grid-header-region',
        'data-grid-header-sales',
      ]);
    expect(screen.getByTestId('export-probe')).toHaveAttribute('data-columns', '3');
  });

  it('renders an explicit empty state without a filter row when columns are plain', () => {
    const plainColumns: DataGridColumn<Row, 'name'>[] = [{
      key: 'name',
      label: 'Nume',
      value: (row) => row.name,
      render: (row) => row.name,
      hideable: false,
    }];

    render(
      <DataGrid
        title="Gol"
        rows={[]}
        columns={plainColumns}
        rowKey={(row) => row.id}
        exportFilename="gol"
        exportSheetName="Gol"
        emptyLabel="Fără date"
      />,
    );

    expect(screen.getByText('Fără date')).toBeInTheDocument();
    expect(screen.getByText('0 înregistrări')).toBeInTheDocument();
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Coloane'));
    expect(screen.getByRole('checkbox', { name: 'Afișează Nume' })).toBeDisabled();
  });
});
