import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { requestSignal, setCsrfTokenProvider } from '../api/client';
import type {
  RetailSessionLogoutResponse,
  RetailSessionProfileResponse,
  RetailSessionStatusResponse,
} from '../api/generated/contracts';
import { decodeRetail } from '../api/generated/decoded';
import { bindRetailBrowserSession, clearRetailBrowserSession } from './browserSession';

export type SessionProfile = RetailSessionProfileResponse;

export type SessionUser = {
  profile: SessionProfile;
};

interface AuthContextValue {
  user: SessionUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  logoutError: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
}

export const LOGOUT_UNCONFIRMED_MESSAGE = 'Deconectarea nu a putut fi confirmată. Încearcă din nou.';

/**
 * Ask the server to revoke the session. Resolves to the provider logout URL only
 * when revocation is confirmed and the response carries a usable URL; every other
 * outcome (network, timeout, non-2xx, invalid body, missing URL) throws or resolves
 * to null so the caller never clears local state on an unconfirmed logout.
 */
async function requestServerLogout(csrfToken: string | null): Promise<string | null> {
  const response = await fetch('/auth/session/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
    signal: requestSignal(undefined, 10_000),
  });
  if (!response.ok) throw new Error(`Session logout failed: ${response.status}`);
  const payload = decodeRetail<
    'session_logout_auth_session_logout_post',
    RetailSessionLogoutResponse
  >('session_logout_auth_session_logout_post', await response.json());
  return typeof payload.logout_url === 'string' && payload.logout_url.trim().length > 0
    ? payload.logout_url
    : null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  onSessionCleared,
}: {
  children: ReactNode;
  onSessionCleared?: () => void;
}) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState(false);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const csrfRef = useRef<string | null>(null);

  useEffect(() => {
    setCsrfTokenProvider(() => csrfRef.current);
    return () => setCsrfTokenProvider(null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    const init = async () => {
      try {
        const response = await fetch('/auth/session', {
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
          signal: requestSignal(controller.signal, 10_000),
        });
        if (response.status === 401) {
          window.location.assign('/auth/session/login');
          return;
        }
        if (!response.ok) throw new Error(`Session bootstrap failed: ${response.status}`);
        const payload = decodeRetail<
          'session_status_auth_session_get',
          RetailSessionStatusResponse
        >('session_status_auth_session_get', await response.json());
        bindRetailBrowserSession(payload.profile.sub);
        csrfRef.current = payload.csrf_token;
        setUser({ profile: payload.profile });
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error('Session bootstrap failed', error);
        setBootstrapError(true);
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };
    void init();
    return () => controller.abort();
  }, [bootstrapAttempt]);

  const login = useCallback(async () => {
    window.location.assign('/auth/session/login');
  }, []);

  const logout = useCallback(async () => {
    setLogoutError(null);
    let logoutUrl: string | null = null;
    try {
      logoutUrl = await requestServerLogout(csrfRef.current);
    } catch (error) {
      console.error('Session logout request failed', error);
    }
    if (logoutUrl === null) {
      // The server session may still be alive: never pretend the logout happened.
      setLogoutError(LOGOUT_UNCONFIRMED_MESSAGE);
      return;
    }
    csrfRef.current = null;
    setUser(null);
    clearRetailBrowserSession();
    onSessionCleared?.();
    window.location.assign(logoutUrl);
  }, [onSessionCleared]);

  const retryBootstrap = useCallback(() => {
    setBootstrapError(false);
    setIsLoading(true);
    setBootstrapAttempt((current) => current + 1);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isAuthenticated: user !== null,
    isLoading,
    logoutError,
    login,
    logout,
  }), [user, isLoading, logoutError, login, logout]);

  if (isLoading) return null;
  if (bootstrapError) {
    return (
      <main className="min-h-screen grid place-items-center bg-slate-50 p-6 dark:bg-slate-950">
        <div role="alert" className="max-w-md rounded-2xl border border-red-200 bg-white p-6 text-center shadow-sm dark:border-red-900 dark:bg-slate-900">
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Sesiunea nu poate fi verificată</h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Verifică rețeaua și încearcă din nou.</p>
          <button type="button" onClick={retryBootstrap} className="mt-4 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500">
            Reîncearcă
          </button>
        </div>
      </main>
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
