// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SalaryArchiveResponse } from '../../api/salaryArchive';
import { SalaryArchivePanel } from './SalaryArchivePanel';
const api = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../../api/salaryArchive', () => ({ fetchSalaryArchive: api.fetch }));
const result: SalaryArchiveResponse = { total_rows: 1, items: [{
  period: '2020-01-01', company_name: 'Mobiup', full_name: 'Agent test', site_code: 'TEST',
  location: 'Magazin test', total_amount: 3000, identity_status: 'conflicting', review_reasons: ['conflict'],
  candidate_person_id: 'private-person-id', source_file: 'sursa.xls', source_sheet: 'Foaie 1', source_row: 4,
  selected: true, pnl_eligible: false, already_recorded: true,
}] };
beforeEach(() => { vi.clearAllMocks(); api.fetch.mockResolvedValue(result); });
describe('SalaryArchivePanel', () => {
  it('keeps unresolved identity separate even when a candidate exists and flags existing official rows', async () => {
    render(<SalaryArchivePanel />);
    await screen.findByText('Agent test');
    expect(screen.getByText('Identitate nereconciliată')).toBeTruthy();
    expect(screen.getByText('Deja în salariile oficiale — nu se adună din nou')).toBeTruthy();
    expect(screen.queryByText('private-person-id')).toBeNull();
    expect(screen.queryByText('Identitate verificată')).toBeNull();
  });
  it('uses store scope over current company and resets pagination when searching', async () => {
    api.fetch.mockResolvedValue({ ...result, total_rows: 101 });
    render(<SalaryArchivePanel globalFilters={{ firma: 'Mobicell', rm: 'Manager', magazin: ['TEST'], agent: [] }} />);
    await screen.findByText('Agent test');
    expect(api.fetch.mock.calls[0]?.[0]).toMatchObject({ site_code: ['TEST'], company_name: undefined, regional: undefined, offset: 0 });
    fireEvent.click(screen.getByText('Înainte'));
    await waitFor(() => expect(api.fetch.mock.calls.at(-1)?.[0].offset).toBe(50));
    fireEvent.change(screen.getByLabelText('Caută nume în istoricul HR'), { target: { value: 'Alt nume' } });
    await waitFor(() => expect(api.fetch.mock.calls.at(-1)?.[0]).toMatchObject({ offset: 0, search: 'Alt nume' }));
  });
});
