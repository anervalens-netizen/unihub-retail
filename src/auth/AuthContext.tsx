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

import { setCsrfTokenProvider } from '../api/client';
import type {
  RetailSessionLogoutResponse,
  RetailSessionProfileResponse,
  RetailSessionStatusResponse,
} from '../api/generated/contracts';

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
  const csrfRef = useRef<string | null>(null);
  const initRef = useRef(false);

  useEffect(() => {
    setCsrfTokenProvider(() => csrfRef.current);
    return () => setCsrfTokenProvider(null);
  }, []);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    const init = async () => {
      const e2eUser = (window as unknown as Record<string, unknown>).__E2E_USER__ as SessionUser | undefined;
      if (e2eUser) {
        setUser(e2eUser);
        setIsLoading(false);
        return;
      }
      try {
        const response = await fetch('/auth/session', {
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
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
        csrfRef.current = payload.csrf_token;
        setUser({ profile: payload.profile });
      } catch (error) {
        console.error('Session bootstrap failed', error);
      } finally {
        setIsLoading(false);
      }
    };
    void init();
  }, []);

  const login = useCallback(async () => {
    window.location.assign('/auth/session/login');
  }, []);

  const logout = useCallback(async () => {
    const response = await fetch('/auth/session/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfRef.current ? { 'X-CSRF-Token': csrfRef.current } : {},
    });
    csrfRef.current = null;
    setUser(null);
    onSessionCleared?.();
    if (response.ok) {
      const payload = await response.json() as RetailSessionLogoutResponse;
      window.location.assign(payload.logout_url || '/auth/session/login');
      return;
    }
    window.location.assign('/auth/session/login');
  }, [onSessionCleared]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isAuthenticated: user !== null,
    isLoading,
    login,
    logout,
  }), [user, isLoading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
