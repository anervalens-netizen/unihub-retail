// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./ASMSubtab', () => ({ ASMSubtab: () => <div>Manageri mock</div> }));
vi.mock('../features/target-calculator/TargetCalculatorPage', () => ({ TargetCalculatorSubtab: () => <div>Target mock</div> }));
vi.mock('./SalariiSubtab', () => ({ SalariiSubtab: () => <div>Salarii mock</div> }));
vi.mock('./PnlSubtab', () => ({ PnlSubtab: () => <div>P&amp;L mock</div> }));
vi.mock('./VisiteSubtab', () => ({ VisiteSubtab: ({ currentMonth, months }: { currentMonth: string; months: string[] }) => <div>FieldOps mock {currentMonth} {months.join(',')}</div> }));

import { Management } from './Management';

describe('Management navigation', () => {
  it('mounts FieldOps under Management with the current month context', async () => {
    render(<Management activeSubTab="fieldops" currentMonth="2026-08" months={['2026-07', '2026-08']} salaryFilters={{ firma: '', rm: '', magazin: [], agent: [] }} />);
    expect(screen.getByRole('tab', { name: 'FieldOps' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText("FieldOps mock 2026-08 2026-07,2026-08")).toBeInTheDocument();
  });
});
