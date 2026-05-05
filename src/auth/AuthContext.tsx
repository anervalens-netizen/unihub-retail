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
import { UserManager, type User } from 'oidc-client-ts';

// ── OIDC config ──────────────────────────────────────────────────────
const OIDC_AUTHORITY = import.meta.env.VITE_OIDC_AUTHORITY ?? 'https://auth.unihub.ro/application/o/unihub-retail/';
const OIDC_CLIENT_ID = import.meta.env.VITE_OIDC_CLIENT_ID ?? '4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t';
const OIDC_REDIRECT_URI = import.meta.env.VITE_OIDC_REDIRECT_URI ?? `${window.location.origin}/auth/callback`;
const OIDC_POST_LOGOUT_URI = import.meta.env.VITE_OIDC_POST_LOGOUT_URI ?? window.location.origin;

const userManager = new UserManager({
  authority: OIDC_AUTHORITY,
  client_id: OIDC_CLIENT_ID,
  redirect_uri: OIDC_REDIRECT_URI,
  post_logout_redirect_uri: OIDC_POST_LOGOUT_URI,
  response_type: 'code',
  scope: 'openid profile email',
  automaticSilentRenew: true,
  monitorSession: false, // authentik session monitoring not needed
});

// ── Context ──────────────────────────────────────────────────────────
interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ─────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const initRef = useRef(false);

  useEffect(() => {
    // Prevent double init in StrictMode
    if (initRef.current) return;
    initRef.current = true;

    const init = async () => {
      try {
        // Check if this is a callback from authentik
        if (window.location.pathname === '/auth/callback') {
          const callbackUser = await userManager.signinRedirectCallback();
          setUser(callbackUser);
          // Clean up the URL — remove auth params
          window.history.replaceState({}, '', '/');
          setIsLoading(false);
          return;
        }

        // Try to get existing user from storage
        const existingUser = await userManager.getUser();
        if (existingUser && !existingUser.expired) {
          setUser(existingUser);
          setIsLoading(false);
        } else {
          // No valid session — redirect to authentik
          setIsLoading(false);
          await userManager.signinRedirect();
        }
      } catch (err) {
        console.error('OIDC init error:', err);
        setIsLoading(false);
        // On any error during callback processing, redirect to login
        await userManager.signinRedirect();
      }
    };

    init();

    // Listen for token refresh events
    const onUserLoaded = (refreshedUser: User) => setUser(refreshedUser);
    const onUserUnloaded = () => setUser(null);
    const onSilentRenewError = (err: Error) => {
      console.error('Silent renew failed:', err);
      // Token couldn't be refreshed — force re-login
      userManager.signinRedirect();
    };

    userManager.events.addUserLoaded(onUserLoaded);
    userManager.events.addUserUnloaded(onUserUnloaded);
    userManager.events.addSilentRenewError(onSilentRenewError);

    return () => {
      userManager.events.removeUserLoaded(onUserLoaded);
      userManager.events.removeUserUnloaded(onUserUnloaded);
      userManager.events.removeSilentRenewError(onSilentRenewError);
    };
  }, []);

  const login = useCallback(async () => {
    await userManager.signinRedirect();
  }, []);

  const logout = useCallback(async () => {
    await userManager.signoutRedirect();
  }, []);

  const getAccessToken = useCallback(() => {
    return user?.access_token ?? null;
  }, [user]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user && !user.expired,
      isLoading,
      login,
      logout,
      getAccessToken,
    }),
    [user, isLoading, login, logout, getAccessToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ── Hook ─────────────────────────────────────────────────────────────
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
}
