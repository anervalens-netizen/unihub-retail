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
import { bindRetailBrowserSession, clearRetailBrowserSession } from './browserSession';

export type SessionProfile = RetailSessionProfileResponse;

export type SessionUser = {
  profile: SessionProfile;
};

interface AuthContextValue {
  user: SessionUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
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
        const payload = await response.json() as RetailSessionStatusResponse;
        if (!payload.profile?.sub || !Array.isArray(payload.profile.groups) || !payload.csrf_token) {
          throw new Error('Session bootstrap returned an invalid contract');
        }
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
    let redirect = '/auth/session/login';
    try {
      const response = await fetch('/auth/session/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: csrfRef.current ? { 'X-CSRF-Token': csrfRef.current } : {},
        signal: requestSignal(undefined, 10_000),
      });
      if (response.ok) {
        const payload = await response.json() as RetailSessionLogoutResponse;
        if (typeof payload.logout_url === 'string' && payload.logout_url) {
          redirect = payload.logout_url;
        }
      }
    } catch (error) {
      console.error('Session logout request failed', error);
    } finally {
      csrfRef.current = null;
      setUser(null);
      clearRetailBrowserSession();
      onSessionCleared?.();
      window.location.assign(redirect);
    }
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
    login,
    logout,
  }), [user, isLoading, login, logout]);

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
