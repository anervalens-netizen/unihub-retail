// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DesktopTopBar } from './DesktopTopBar';
import { MobileFilterSheet, MobileFloatingFilter } from './MainLayoutMobile';
import type { MainLayoutFilterModel } from './useMainLayoutFilters';

const filters = { firma: 'Toate', rm: 'Toti', magazin: [], agent: [] };
const model = {
  options: { firme: [], regionali: [], asmi: [], magazine: [], agenti: [] },
  regionals: [],
  stores: [],
  agents: [],
  activeCount: 0,
  hasMobileFilters: false,
  reset: vi.fn(),
} as MainLayoutFilterModel;

describe('Saved Views responsive shell placement', () => {
  it('renders the desktop Saved Views slot beside top-bar controls', () => {
    render(
      <DesktopTopBar
        activeTab="hub"
        mgmtSubTab="asm"
        showFilterButton
        onOpenFilter={vi.fn()}
        filters={filters}
        savedViews={<button type="button">Vederi personale</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Vederi personale' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filtre' })).toBeInTheDocument();
  });

  it('keeps Saved Views reachable on mobile when the current surface has no filters', () => {
    render(
      <MobileFilterSheet
        open
        onOpenChange={vi.fn()}
        filters={filters}
        setFilters={vi.fn()}
        model={model}
        showFilters={false}
        savedViews={<div>Vederi personale</div>}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Context' })).toBeInTheDocument();
    expect(screen.getByText('Vederi personale')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Filtre active' })).not.toBeInTheDocument();
    expect(screen.queryByText('Firma')).not.toBeInTheDocument();
  });

  it('uses one mobile context button for filters plus Saved Views', () => {
    const { rerender } = render(
      <MobileFloatingFilter count={2} onOpen={vi.fn()} showFilters hasSavedViews />,
    );
    expect(screen.getByRole('button', { name: 'Context, 2 filtre active și vederi salvate' })).toBeInTheDocument();

    rerender(
      <MobileFloatingFilter count={0} onOpen={vi.fn()} showFilters={false} hasSavedViews />,
    );
    expect(screen.getByRole('button', { name: 'Vederi salvate' })).toBeInTheDocument();
  });
});
