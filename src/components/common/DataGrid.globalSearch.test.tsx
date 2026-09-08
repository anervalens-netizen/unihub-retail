// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../ExportTableButton', () => ({
  ExportTableButton: ({ rows }: { rows: unknown[] }) => (
    <output data-testid="global-search-export" data-rows={rows.length} />
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
    filter: { kind: 'text' },
    defaultDirection: 'asc',
    hideable: false,
  },
  {
    key: 'region',
    label: 'Regiune',
    value: (row) => row.region,
    render: (row) => row.region,
    filter: {
      kind: 'enum',
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
  },
];

function renderedNames(): string[] {
  return screen.queryAllByTestId('data-grid-row').map((row) =>
    within(row).getAllByRole('cell')[0]?.textContent ?? '',
  );
}

describe('DataGrid global search', () => {
  it('searches displayed columns and composes with filters, reset and export', () => {
    render(
      <DataGrid
        title="Regional"
        rows={rows}
        columns={columns}
        initialSort={[{ key: 'sales', direction: 'desc' }]}
        rowKey={(row) => row.id}
        exportFilename="regional"
        exportSheetName="Regional"
      />,
    );

    const table = screen.getByRole('table', { name: 'Regional' });
    const search = screen.getByRole('searchbox', {
      name: 'Caută în coloanele afișate din Regional',
    });

    expect(table.id).not.toBe('');
    expect(search).toHaveAttribute('aria-controls', table.id);

    fireEvent.change(search, { target: { value: 'ana nord' } });
    expect(renderedNames()).toEqual(['b:Ana']);
    expect(screen.getByText(/1 din 4 înregistrări/)).toBeInTheDocument();
    expect(screen.getByTestId('global-search-export')).toHaveAttribute('data-rows', '1');
    expect(screen.getByRole('button', { name: 'Șterge filtrele (1)' })).toBeInTheDocument();

    fireEvent.click(screen.getByText('Coloane'));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    expect(screen.queryByTestId('data-grid-header-region')).not.toBeInTheDocument();
    expect(renderedNames()).toEqual([]);
    expect(screen.getByTestId('global-search-export')).toHaveAttribute('data-rows', '0');

    fireEvent.click(screen.getByRole('button', { name: 'Resetează coloanele' }));
    expect(screen.getByTestId('data-grid-header-region')).toBeInTheDocument();
    expect(renderedNames()).toEqual(['b:Ana']);

    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minim Vânzări' }), {
      target: { value: '250' },
    });
    expect(renderedNames()).toEqual([]);
    expect(screen.getByRole('button', { name: 'Șterge filtrele (2)' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Șterge filtrele (2)' }));
    expect(search).toHaveValue('');
    expect(screen.getByRole('spinbutton', { name: 'Minim Vânzări' })).toHaveValue(null);
    expect(renderedNames()).toEqual(['b:Ana', 'c:Ștefan', 'a:Ana', 'd:Mihai']);
    expect(screen.getByTestId('global-search-export')).toHaveAttribute('data-rows', '4');
  });
});
