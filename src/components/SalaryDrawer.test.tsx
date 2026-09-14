// @vitest-environment jsdom

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ history: vi.fn() }));
vi.mock('../api/salarii', () => ({ fetchSalaryAgentHistory: api.history }));
vi.mock('recharts', () => {
  const Element = ({ children }: { children?: unknown }) => <div>{children as never}</div>;
  return { Bar: Element, BarChart: Element, CartesianGrid: Element, Cell: Element, ResponsiveContainer: Element, Tooltip: Element, XAxis: Element, YAxis: Element };
});

import { SalaryDrawer } from './SalaryDrawer';

const history = {
  total: 3000,
  avg: 3000,
  avg_month_count: 1,
  month_count: 1,
  records: [{ year: 2026, month: 8, company_name: 'Mobicell', locatie: 'Alfa', site_code: 'S1', total_salary: 3000 }],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('SalaryDrawer', () => {
  beforeEach(() => api.history.mockReset());

  it('guards delayed retry results when the selected person changes', async () => {
    const retry = deferred<typeof history>();
    const replacement = deferred<typeof history>();
    api.history.mockImplementationOnce(() => Promise.reject(new Error('offline'))).mockReturnValueOnce(retry.promise).mockReturnValueOnce(replacement.promise);
    const { rerender } = render(<SalaryDrawer personId="person-a" fullName="Person A" isOpen onClose={vi.fn()} />);
    expect(await screen.findByText('Nu s-au putut încărca datele')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    rerender(<SalaryDrawer personId="person-b" fullName="Person B" isOpen onClose={vi.fn()} />);

    await act(async () => retry.resolve(history));
    expect(screen.queryByText('Person A')).not.toBeInTheDocument();
    await act(async () => replacement.resolve(history));
    expect(await screen.findByText('Person B')).toBeInTheDocument();
  });

  it('provides dialog semantics, focus, escape, restoration, and loading/error controls', async () => {
    const pending = deferred<typeof history>();
    const close = vi.fn();
    const { rerender } = render(<><button data-testid="trigger">Open</button><SalaryDrawer personId="person-a" fullName="Person A" isOpen={false} onClose={close} /></>);
    const trigger = screen.getByTestId('trigger');
    trigger.focus();
    api.history.mockReturnValueOnce(pending.promise).mockImplementationOnce(() => Promise.reject(new Error('offline')));
    rerender(<><button data-testid="trigger">Open</button><SalaryDrawer personId="person-a" fullName="Person A" isOpen onClose={close} /></>);
    expect(screen.getByRole('dialog', { name: 'Person A' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Închide istoricul salarial' })).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(close).toHaveBeenCalledOnce();
    rerender(<><button data-testid="trigger">Open</button><SalaryDrawer personId="person-a" fullName="Person A" isOpen={false} onClose={close} /></>);
    expect(trigger).toHaveFocus();

    rerender(<SalaryDrawer personId="person-a" fullName="Person A" isOpen onClose={close} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    await act(async () => pending.resolve(history));
  });
});
