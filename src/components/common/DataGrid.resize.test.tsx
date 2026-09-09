// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../ExportTableButton', () => ({
  ExportTableButton: () => null,
}));

import { DataGrid, type DataGridColumn } from './DataGrid';
import {
  DATA_GRID_COLUMN_MAX_WIDTH,
  DATA_GRID_COLUMN_MIN_WIDTH,
} from './DataGridControls';

type Key = 'name' | 'region' | 'sales';
interface Row { id: string; name: string; region: string; sales: number }

const rows: Row[] = [
  { id: 'a', name: 'Ana', region: 'Nord', sales: 100 },
  { id: 'b', name: 'Mihai', region: 'Sud', sales: 200 },
];
const columns: DataGridColumn<Row, Key>[] = [
  { key: 'name', label: 'Nume', value: (row) => row.name, render: (row) => row.name, hideable: false },
  { key: 'region', label: 'Regiune', value: (row) => row.region, render: (row) => row.region },
  { key: 'sales', label: 'Vânzări', value: (row) => row.sales, render: (row) => row.sales },
];

function renderGrid(onSortChange = vi.fn()) {
  render(
    <DataGrid
      title="Regional"
      rows={rows}
      columns={columns}
      onSortChange={onSortChange}
      rowKey={(row) => row.id}
      exportFilename="regional"
      exportSheetName="Regional"
    />,
  );
  return onSortChange;
}

function resizeHandle(label = 'Regiune') {
  return screen.getByRole('separator', { name: `Redimensionează ${label}` });
}

function stubHeaderWidth(handle: HTMLElement, width: number) {
  vi.spyOn(handle.parentElement as HTMLElement, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: width,
    bottom: 30,
    width,
    height: 30,
    toJSON: () => ({}),
  });
}

describe('DataGrid column resizing', () => {
  it('resizes from the measured width with keyboard steps without sorting', () => {
    const onSortChange = renderGrid();
    const table = screen.getByRole('table', { name: 'Regional' });
    const handle = resizeHandle();
    stubHeaderWidth(handle, 120);
    expect(table).toHaveClass('w-full');
    expect(table).not.toHaveClass('w-max');

    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(handle).toHaveAttribute('aria-valuenow', '136');
    expect(screen.getByTestId('data-grid-header-region')).toHaveStyle({ width: '136px' });
    expect(table).toHaveClass('w-max');
    expect(table).not.toHaveClass('w-full');
    expect(onSortChange).not.toHaveBeenCalled();

    fireEvent.keyDown(handle, { key: 'ArrowRight', shiftKey: true });
    expect(handle).toHaveAttribute('aria-valuenow', '184');
    expect(onSortChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Sortează după Regiune' }));
    expect(onSortChange).toHaveBeenCalledTimes(1);
  });

  it('clamps pointer dragging to the declared minimum and maximum widths', () => {
    renderGrid();
    const handle = resizeHandle();
    stubHeaderWidth(handle, 120);

    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: -1000 });
    expect(handle).toHaveAttribute('aria-valuenow', String(DATA_GRID_COLUMN_MIN_WIDTH));
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: -1000 });

    fireEvent.pointerDown(handle, { pointerId: 2, clientX: 100 });
    fireEvent.pointerMove(handle, { pointerId: 2, clientX: 2000 });
    expect(handle).toHaveAttribute('aria-valuenow', String(DATA_GRID_COLUMN_MAX_WIDTH));
    fireEvent.pointerUp(handle, { pointerId: 2, clientX: 2000 });
  });

  it('retains an in-session width while a column is hidden and shown again', () => {
    renderGrid();
    const table = screen.getByRole('table', { name: 'Regional' });
    const handle = resizeHandle();
    stubHeaderWidth(handle, 120);
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(handle).toHaveAttribute('aria-valuenow', '136');
    expect(table).toHaveClass('w-max');

    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));
    expect(screen.queryByRole('separator', { name: 'Redimensionează Regiune' })).not.toBeInTheDocument();
    expect(table).toHaveClass('w-full');
    expect(table).not.toHaveClass('w-max');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Regiune' }));

    expect(resizeHandle()).toHaveAttribute('aria-valuenow', '136');
    expect(screen.getByTestId('data-grid-header-region')).toHaveStyle({ width: '136px' });
    expect(table).toHaveClass('w-max');
  });

  it('resets one width on double click', () => {
    renderGrid();
    const handle = resizeHandle();
    stubHeaderWidth(handle, 120);
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(handle).toHaveAttribute('aria-valuetext', '136 pixeli');

    fireEvent.doubleClick(handle);
    expect(handle).toHaveAttribute('aria-valuetext', 'Lățime automată');
    expect(screen.getByTestId('data-grid-header-region').style.width).toBe('');
    expect(screen.getByRole('table', { name: 'Regional' })).toHaveClass('w-full');
  });

  it('resets all widths without resetting visibility or order', () => {
    renderGrid();
    const regionHandle = resizeHandle();
    stubHeaderWidth(regionHandle, 120);
    fireEvent.keyDown(regionHandle, { key: 'ArrowRight' });

    const salesHandle = resizeHandle('Vânzări');
    stubHeaderWidth(salesHandle, 140);
    fireEvent.keyDown(salesHandle, { key: 'ArrowRight' });

    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Afișează Vânzări' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mută Regiune la stânga' }));
    fireEvent.click(screen.getByRole('button', { name: 'Resetează lățimile' }));

    expect(resizeHandle()).toHaveAttribute('aria-valuetext', 'Lățime automată');
    expect(screen.queryByTestId('data-grid-header-sales')).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^data-grid-header-/).map((header) => header.dataset.testid))
      .toEqual(['data-grid-header-region', 'data-grid-header-name']);
  });
});
