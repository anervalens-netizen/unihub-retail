// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from './AuthContext';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.restoreAllMocks();
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
      .mockResolvedValueOnce(new Response(JSON.stringify({
        profile: { sub: 'user-1', groups: [] },
        csrf_token: 'csrf',
      }), { status: 200 }));
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

  it('clears the local session when the server logout request fails', async () => {
    const onSessionCleared = vi.fn();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({
        profile: { sub: 'user-1', groups: [] },
        csrf_token: 'csrf',
      }), { status: 200 }))
      .mockRejectedValueOnce(new TypeError('offline'));

    function LogoutButton() {
      const { logout } = useAuth();
      return <button type="button" onClick={() => void logout()}>Ieșire</button>;
    }

    render(
      <AuthProvider onSessionCleared={onSessionCleared}>
        <LogoutButton />
      </AuthProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Ieșire' }));

    await waitFor(() => expect(onSessionCleared).toHaveBeenCalledOnce());
  });

  it('validates the server logout response before clearing the session', async () => {
    const onSessionCleared = vi.fn();
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({
        profile: { sub: 'user-1', groups: [] },
        csrf_token: 'csrf',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        logout_url: '/auth/session/login?logged_out=1',
      }), { status: 200 }));

    function LogoutButton() {
      const { logout } = useAuth();
      return <button type="button" onClick={() => void logout()}>Ieșire</button>;
    }

    render(
      <AuthProvider onSessionCleared={onSessionCleared}>
        <LogoutButton />
      </AuthProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Ieșire' }));

    await waitFor(() => expect(onSessionCleared).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
