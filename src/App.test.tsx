// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const authState = {
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  user: null,
};

const monthsState = {
  months: [] as string[],
  status: 'empty' as 'empty' | 'unavailable' | 'session_expired' | 'ready',
  isLoading: false,
  isFetching: false,
  error: null,
  retry: vi.fn(),
  setMonths: vi.fn(),
};

vi.mock('./auth/AuthContext', () => ({
  useAuth: () => authState,
}));

vi.mock('./hooks/useAvailableMonths', () => ({
  useAvailableMonths: () => monthsState,
}));

vi.mock('./auth/usePnlCapability', () => ({
  usePnlCapability: () => ({ permissionPending: false, hasPnlAccess: false }),
}));

vi.mock('./components/MainLayout', () => ({
  MainLayout: () => <div data-testid="main-layout" />,
}));

vi.mock('./screenLoaders', () => ({
  loadAgentsScreen: vi.fn(),
  loadCampaignsScreen: vi.fn(),
  loadDashboardScreen: vi.fn(),
  loadManagementScreen: vi.fn(),
  loadSettingsScreen: vi.fn(),
}));

import App from './App';

describe('App bootstrap boundary', () => {
  beforeEach(() => {
    authState.isAuthenticated = false;
    authState.isLoading = false;
    authState.user = null;
    monthsState.months = [];
    monthsState.status = 'empty';
    monthsState.isLoading = false;
    monthsState.retry.mockReset();
  });

  it('keeps unauthenticated bootstrap actionable', () => {
    render(<App />);

    expect(screen.getByText('Nu ești autentificat.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Login' })).toBeInTheDocument();
  });

  it('surfaces unavailable months with an in-place retry', () => {
    authState.isAuthenticated = true;
    monthsState.status = 'unavailable';

    render(<App />);

    expect(screen.getByText('Lunile disponibile nu au putut fi încărcate.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reîncearcă' })).toBeInTheDocument();
  });

  it('does not offer blind retry after session expiry', () => {
    authState.isAuthenticated = true;
    monthsState.status = 'session_expired';

    render(<App />);

    expect(screen.getByText(/Sesiunea a expirat/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reîncearcă' })).not.toBeInTheDocument();
  });
});
