// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { downloadExcelTable } from '../../lib/tableExport';
import type { IncentiveTopAgent, PromoTopStore } from '../../api/generated/runtime-types';
import { IncentiveAgentsTable, IncentiveStoresTable } from './IncentiveTables';

vi.mock('../../lib/tableExport', () => ({ downloadExcelTable: vi.fn() }));

describe('Incentive Excel exports', () => {
  it('exports the row location code and RM for both cards without changing amounts', async () => {
    const identity = { site_code: 'ALBACAROLINA', regional: 'Bogdana Costan', store_name: 'ALBACAROLINA - CAROLINA MALL ALBA', firma: 'MobiCell', achievement: 1.0233, incentive_potential: 720 };
    const store: PromoTopStore = { ...identity, qty: 77, incentive_value: 720, total_qty: 0, category_qty: 0, promo_bons: 0 };
    const agent: IncentiveTopAgent = { ...identity, agent_name: 'Agent 1', qty_sold: 77, val_incentive: 720 };
    render(<><IncentiveStoresTable rows={[store]} month="2026-08" /><IncentiveAgentsTable rows={[agent]} month="2026-08" /></>);
    screen.getAllByRole('button', { name: 'Excel' }).forEach(button => fireEvent.click(button));
    await waitFor(() => expect(downloadExcelTable).toHaveBeenCalledTimes(2));
    for (const [request] of vi.mocked(downloadExcelTable).mock.calls) {
      const values = Object.fromEntries(request.columns.map(column => [column.header, column.value(request.rows[0], 0)]));
      expect(values).toMatchObject({ 'Cod locație': 'ALBACAROLINA', 'Manager (RM)': 'Bogdana Costan', 'Cant.': 77, 'Val Inc.': 720, 'Incentive potential': 720 });
      expect(request.filename).toMatch(/^focus-incentive-(magazine|agenti)-2026-08$/);
    }
  });
});
