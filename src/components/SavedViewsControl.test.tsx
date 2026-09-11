// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  listSavedViews: vi.fn(), createSavedView: vi.fn(), deleteSavedView: vi.fn(),
  toRetailContextUrlState: vi.fn((state) => ({
    tab: state.tab, period: state.period ?? undefined, filters: state.filters,
    hubSection: state.tab === 'hub' ? state.section : undefined,
  })),
}));
vi.mock('../api/savedViews', () => api);
import { SavedViewsControl } from './SavedViewsControl';

const filters = { firma: 'Arsis', rm: 'RM Est', magazin: ['M1'], agent: ['A1'] };
const currentState = { tab: 'hub' as const, period: '2026-09', filters, hubSection: 'history' as const };
const view = {
  id: 3, module_id: 'hub' as const, name: 'Istoric Est',
  state: { tab: 'hub' as const, period: '2026-08', filters, section: 'history' },
  schema_version: 1 as const, created_at: '2026-09-11T10:00:00Z', updated_at: '2026-09-11T10:00:00Z',
};

describe('SavedViewsControl', () => {
  beforeEach(() => {
    api.listSavedViews.mockReset().mockResolvedValue([view]);
    api.createSavedView.mockReset(); api.deleteSavedView.mockReset().mockResolvedValue(undefined);
    api.toRetailContextUrlState.mockClear(); vi.restoreAllMocks();
  });

  it('loads lazily on desktop and applies through the canonical Retail URL', async () => {
    const navigate = vi.fn();
    render(<SavedViewsControl currentState={currentState} mode="desktop" navigate={navigate} />);
    expect(api.listSavedViews).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Vederi' }));
    expect(await screen.findByText('Istoric Est')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Aplică vederea Istoric Est' }));
    expect(api.toRetailContextUrlState).toHaveBeenCalledWith(view.state);
    expect(navigate).toHaveBeenCalledWith('/hub?source_context=retail&period=2026-08&firma=Arsis&rm=RM+Est&magazin=M1&agent=A1&section=history');
  });

  it('creates a named view from the exact current canonical state', async () => {
    const created = { ...view, id: 4, name: 'Noua vedere', state: { ...view.state, period: '2026-09' } };
    api.createSavedView.mockResolvedValue(created);
    render(<SavedViewsControl currentState={currentState} mode="desktop" />);
    fireEvent.click(screen.getByRole('button', { name: 'Vederi' }));
    await screen.findByText('Istoric Est');
    fireEvent.change(screen.getByPlaceholderText('Nume vedere...'), { target: { value: '  Noua vedere  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvează' }));
    await waitFor(() => expect(api.createSavedView).toHaveBeenCalledWith('Noua vedere', currentState));
    expect(await screen.findByText('Noua vedere')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Nume vedere...')).toHaveValue('');
  });

  it('deletes only after explicit confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<SavedViewsControl currentState={currentState} mode="desktop" />);
    fireEvent.click(screen.getByRole('button', { name: 'Vederi' }));
    await screen.findByText('Istoric Est');
    fireEvent.click(screen.getByRole('button', { name: 'Șterge vederea Istoric Est' }));
    await waitFor(() => expect(api.deleteSavedView).toHaveBeenCalledWith(3));
    expect(confirm).toHaveBeenCalled();
    expect(screen.queryByText('Istoric Est')).not.toBeInTheDocument();
  });

  it('loads immediately in the mobile context sheet and surfaces errors', async () => {
    api.listSavedViews.mockRejectedValue(new Error('offline'));
    render(<SavedViewsControl currentState={currentState} mode="mobile" />);
    expect(screen.getByRole('heading', { name: 'Vederi salvate' })).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('Vederile salvate nu au putut fi încărcate.');
  });

  it('keeps browse/apply available when the current screen is not saveable', async () => {
    const navigate = vi.fn();
    render(<SavedViewsControl currentState={null} mode="desktop" navigate={navigate} />);
    fireEvent.click(screen.getByRole('button', { name: 'Vederi' }));
    expect(await screen.findByText('Istoric Est')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvează' })).not.toBeInTheDocument();
    expect(screen.getByText(/Contextul curent nu poate fi salvat/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Aplică vederea Istoric Est' }));
    expect(navigate).toHaveBeenCalledWith('/hub?source_context=retail&period=2026-08&firma=Arsis&rm=RM+Est&magazin=M1&agent=A1&section=history');
  });
});
