// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, LOGOUT_UNCONFIRMED_MESSAGE, useAuth } from './AuthContext';

const fetchMock = vi.fn();
const assignMock = vi.fn();

function sessionResponse() {
  return new Response(JSON.stringify({
    profile: { sub: 'user-1', groups: [] },
    csrf_token: 'csrf',
  }), { status: 200 });
}

function logoutResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function LogoutHarness() {
  const { logout, isAuthenticated, logoutError } = useAuth();
  return (
    <div>
      <span data-testid="auth-state">{isAuthenticated ? 'autentificat' : 'anonim'}</span>
      <span data-testid="logout-error">{logoutError ?? 'fără eroare'}</span>
      <button type="button" onClick={() => void logout()}>Ieșire</button>
    </div>
  );
}

function renderHarness(onSessionCleared?: () => void) {
  return render(
    <AuthProvider onSessionCleared={onSessionCleared}>
      <LogoutHarness />
    </AuthProvider>,
  );
}

async function clickLogout() {
  fireEvent.click(await screen.findByRole('button', { name: 'Ieșire' }));
}

beforeEach(() => {
  fetchMock.mockReset();
  assignMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { assign: assignMock },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('AuthProvider bootstrap recovery', () => {
  it('shows an explicit retry UI on a network error', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('offline'));
    render(<AuthProvider><div>aplicație</div></AuthProvider>);

    expect(await screen.findByRole('alert')).toHaveTextContent('Sesiunea nu poate fi verificată');
    expect(screen.queryByText('aplicație')).not.toBeInTheDocument();
  });

  it('recovers after retrying a failed bootstrap', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(sessionResponse());
    render(<AuthProvider><div>aplicație</div></AuthProvider>);

    fireEvent.click(await screen.findByRole('button', { name: 'Reîncearcă' }));

    await waitFor(() => expect(screen.getByText('aplicație')).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('rejects an invalid session response and offers recovery', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ profile: {} }), { status: 200 }));
    render(<AuthProvider><div>aplicație</div></AuthProvider>);

    expect(await screen.findByRole('alert')).toHaveTextContent('Sesiunea nu poate fi verificată');
  });
});

describe('AuthProvider logout confirmation', () => {
  it('clears the local session and redirects only on a confirmed server logout', async () => {
    const onSessionCleared = vi.fn();
    const logoutUrl = 'https://auth.example.invalid/application/o/unihub-retail/end-session/?x=1';
    fetchMock
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(logoutResponse({ logout_url: logoutUrl }));

    renderHarness(onSessionCleared);
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith(logoutUrl));
    expect(assignMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('auth-state')).toHaveTextContent('anonim');
    expect(screen.getByTestId('logout-error')).toHaveTextContent('fără eroare');
    expect(onSessionCleared).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'POST',
      headers: { 'X-CSRF-Token': 'csrf' },
    });
  });

  it('preserves the local session and the CSRF token when the request fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock.mockResolvedValueOnce(sessionResponse()).mockRejectedValue(new TypeError('offline'));

    renderHarness();
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(screen.getByTestId('logout-error')).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE));
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');
    expect(assignMock).not.toHaveBeenCalled();

    await clickLogout();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({
      headers: { 'X-CSRF-Token': 'csrf' },
    });
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('preserves the local session when the server refuses to revoke it', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Session logout temporarily unavailable' }), { status: 503 }));

    renderHarness();
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(screen.getByTestId('logout-error')).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE));
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');
    expect(assignMock).not.toHaveBeenCalled();
  });

  it.each([
    ['missing', {}],
    ['empty', { logout_url: '' }],
    ['blank', { logout_url: '   ' }],
    ['not a string', { logout_url: 42 }],
  ])('preserves the local session when the success body has a %s logout_url', async (_label, body) => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock.mockResolvedValueOnce(sessionResponse()).mockResolvedValueOnce(logoutResponse(body));

    renderHarness();
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(screen.getByTestId('logout-error')).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE));
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('preserves the local session when the success body is not valid JSON', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(new Response('not json', { status: 200 }));

    renderHarness();
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(screen.getByTestId('logout-error')).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE));
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('clears the previous error and completes logout when the retry is confirmed', async () => {
    const onSessionCleared = vi.fn();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock
      .mockResolvedValueOnce(sessionResponse())
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(logoutResponse({ logout_url: '/auth/session/login?logged_out=1' }));

    renderHarness(onSessionCleared);
    expect(await screen.findByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();
    await waitFor(() => expect(screen.getByTestId('logout-error')).toHaveTextContent(LOGOUT_UNCONFIRMED_MESSAGE));
    expect(screen.getByTestId('auth-state')).toHaveTextContent('autentificat');

    await clickLogout();

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith('/auth/session/login?logged_out=1'));
    expect(screen.getByTestId('logout-error')).toHaveTextContent('fără eroare');
    expect(screen.getByTestId('auth-state')).toHaveTextContent('anonim');
    expect(onSessionCleared).toHaveBeenCalledOnce();
  });

  it('never rejects towards the caller when logout cannot be confirmed', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock.mockResolvedValueOnce(sessionResponse()).mockRejectedValue(new TypeError('offline'));
    const rejections: unknown[] = [];

    function RejectionProbe() {
      const { logout } = useAuth();
      return <button type="button" onClick={() => { void logout().catch((error: unknown) => rejections.push(error)); }}>Ieșire</button>;
    }

    render(<AuthProvider><RejectionProbe /></AuthProvider>);
    fireEvent.click(await screen.findByRole('button', { name: 'Ieșire' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(rejections).toEqual([]);
  });
});
