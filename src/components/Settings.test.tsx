// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock('../auth/permissions', () => ({
  canAdministerImports: () => false,
  canExportReports: () => false,
}));

vi.mock('../hooks/useAvailableMonths', () => ({
  useAvailableMonths: () => ({
    months: [],
    status: 'empty',
    isLoading: false,
    isFetching: false,
    error: null,
    staleAt: null,
    retry: vi.fn(),
    setMonths: vi.fn(),
  }),
}));

import { Settings } from './Settings';

describe('Settings permission boundary', () => {
  it('keeps restricted users on preferences and hides server operations', () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <Settings theme="light" setTheme={vi.fn()} onImportCompleted={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('tablist', { name: 'Secțiuni Setări' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Preferințe', selected: true })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Importuri' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Exporturi' })).not.toBeInTheDocument();
    expect(screen.getByText(/disponibile doar rolurilor manageriale/)).toBeInTheDocument();
  });
});
