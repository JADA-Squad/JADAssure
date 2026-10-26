import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, setAuthToken, setUnauthorizedHandler } from "../../api/client";
import type { Me, TokenResponse } from "../../api/types";

const STORAGE_KEY = "jadassure.session";

interface Session {
  token: string;
  expiresAt: string;
  me: Me;
}

interface AuthState {
  session: Session | null;
  /** True until a stored session has been checked against the API. */
  restoring: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: SignupInput) => Promise<void>;
  logout: () => void;
}

export interface SignupInput {
  organization_name: string;
  business_type: string;
  name: string;
  email: string;
  password: string;
}

const AuthContext = createContext<AuthState | null>(null);

function readStored(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    return new Date(s.expiresAt).getTime() > Date.now() ? s : null;
  } catch {
    return null;
  }
}

function store(s: Session | null) {
  try {
    if (s) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);

  const apply = useCallback((s: Session | null) => {
    setAuthToken(s?.token ?? null);
    store(s);
    setSession(s);
  }, []);

  const logout = useCallback(() => apply(null), [apply]);

  // Restore a stored session, re-reading /me so role changes since login are picked up.
  useEffect(() => {
    const stored = readStored();
    if (!stored) {
      setRestoring(false);
      return;
    }
    setAuthToken(stored.token);
    api<Me>("/auth/me")
      .then((me) => apply({ ...stored, me }))
      .catch(() => apply(null))
      .finally(() => setRestoring(false));
  }, [apply]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Return to login when the token expires, even without further requests.
  useEffect(() => {
    if (!session) return;
    const ms = new Date(session.expiresAt).getTime() - Date.now();
    const timer = window.setTimeout(logout, Math.max(ms, 0));
    return () => window.clearTimeout(timer);
  }, [session, logout]);

  const fromToken = useCallback(
    (t: TokenResponse) => apply({ token: t.access_token, expiresAt: t.expires_at, me: t.me }),
    [apply],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      fromToken(await api<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }));
    },
    [fromToken],
  );

  const signup = useCallback(
    async (input: SignupInput) => {
      fromToken(await api<TokenResponse>("/auth/signup", { method: "POST", body: JSON.stringify(input) }));
    },
    [fromToken],
  );

  const value = useMemo(() => ({ session, restoring, login, signup, logout }), [session, restoring, login, signup, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
