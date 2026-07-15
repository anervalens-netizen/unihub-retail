import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { BreakdownTable, breakdownViewportHeight, type BreakdownColumn } from './BreakdownTable';

type Row = {
  id: string;
  name: string;
  sales: number;
};

type SortKey = 'name' | 'sales';

const rows: Row[] = [
  { id: 'first', name: 'Magazin Nord', sales: 1250 },
  { id: 'second', name: 'Magazin Sud', sales: 980 },
];

const columns: BreakdownColumn<Row, SortKey>[] = [
  {
    key: 'name',
    label: 'Magazin',
    cellClassName: 'text-left',
    render: (row) => row.name,
  },
  {
    key: 'sales',
    label: 'Vanzari',
    render: (row) => row.sales.toLocaleString('ro-RO'),
  },
];

function renderTable(tableRows: Row[] = rows) {
  return renderToStaticMarkup(
    createElement(BreakdownTable<Row, SortKey>, {
      title: 'Magazine',
      subtitle: `${tableRows.length} magazine`,
      rows: tableRows,
      columns,
      sortKey: 'sales',
      sortDirection: 'desc',
      onSort: vi.fn(),
      rowKey: (row) => row.id,
      exportFilename: 'magazine',
      exportSheetName: 'Magazine',
      exportColumns: [
        { header: 'Magazin', value: (row) => row.name },
        { header: 'Vanzari', value: (row) => row.sales },
      ],
    }),
  );
}

describe('BreakdownTable', () => {
  it('sizes short tables by their actual row count and caps long tables', () => {
    expect(breakdownViewportHeight(0)).toBe('3rem');
    expect(breakdownViewportHeight(2)).toBe('6.5rem');
    expect(breakdownViewportHeight(74)).toBe('26rem');
  });

  it('renders the shared heading, sortable columns and every row', () => {
    const html = renderTable();

    expect(html).toContain('Magazine');
    expect(html).toContain('2 magazine');
    expect(html).toContain('Magazin Nord');
    expect(html).toContain('Magazin Sud');
    expect(html).toContain('Vanzari');
    const tableBody = html.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1] ?? '';
    expect(tableBody.match(/<tr/g)).toHaveLength(2);
    expect(html).toContain('title="Export Excel"');
    expect(html).toContain('style="height:6.5rem"');
    expect(html).not.toContain('disabled=""');
  });

  it('disables export when there are no rows', () => {
    const html = renderTable([]);

    expect(html).toContain('0 magazine');
    expect(html).toContain('disabled=""');
  });
});
