// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LOGOUT_UNCONFIRMED_MESSAGE } from '../auth/AuthContext';
import { MainLayout } from './MainLayout';

const baseProps = {
  activeTab: 'hub' as const,
  setActiveTab: vi.fn(),
  isFilterOpen: false,
  setIsFilterOpen: vi.fn(),
  filters: { firma: 'Toate', rm: 'Toti', magazin: [], agent: [] },
  setFilters: vi.fn(),
  filterMonth: '2026-01',
  theme: 'light',
  setTheme: vi.fn(),
  mgmtSubTab: 'asm' as const,
};

describe('MainLayout logout failure surface', () => {
  it('renders an accessible alert when the logout could not be confirmed', () => {
    render(<MainLayout {...baseProps} logoutError={LOGOUT_UNCONFIRMED_MESSAGE}><div>conținut</div></MainLayout>);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE);
    expect(screen.getByText('conținut')).toBeInTheDocument();
  });

  it('renders no alert when the last logout was confirmed or never attempted', () => {
    render(<MainLayout {...baseProps} logoutError={null}><div>conținut</div></MainLayout>);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not surface the logout failure through the bootstrap error screen', () => {
    render(<MainLayout {...baseProps} logoutError={LOGOUT_UNCONFIRMED_MESSAGE}><div>conținut</div></MainLayout>);

    expect(screen.queryByText('Sesiunea nu poate fi verificată')).not.toBeInTheDocument();
  });
});
