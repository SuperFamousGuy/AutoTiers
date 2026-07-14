import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode, Dispatch, SetStateAction } from "react";
import { getMe, login as apiLogin, logout as apiLogout, signup as apiSignup } from "@/api/auth";
import type { User, Profile } from "@/api/types";

interface AuthContextValue {
  loading: boolean;
  user: User | null;
  profiles: Profile[];
  signup: (body: { email: string; password: string; initial_settings?: Record<string, unknown>; initial_rules?: Record<string, Array<{ name: string; enabled: boolean; weight: number }>> }) => Promise<void>;
  login: (body: { email: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setProfiles: Dispatch<SetStateAction<Profile[]>>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  // Monotonic sequence guard. Every refresh() captures the id it was issued
  // with; only the response of the latest-issued call is allowed to mutate
  // state. Without this, two concurrent refresh() calls race — the mount call
  // and the post-email-verification call fire back-to-back, and if the older
  // (pre-verification) /api/auth/me response resolves last it would silently
  // overwrite the just-verified state with stale "unverified" data (#713).
  const refreshSeq = useRef(0);

  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current;
    setLoading(true);
    try {
      const me = await getMe();
      if (seq !== refreshSeq.current) return; // a newer refresh() superseded us
      setUser(me?.user ?? null);
      setProfiles(me?.profiles ?? []);
    } finally {
      // Always clear loading — getMe swallows 401 but a network/5xx
      // error would otherwise leave the app stuck in the loading state.
      // Only the latest call clears loading, so an early-resolving stale
      // call can't drop the spinner while the newest call is still in flight.
      if (seq === refreshSeq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signup = useCallback(async (body: Parameters<AuthContextValue["signup"]>[0]) => {
    const me = await apiSignup(body);
    setUser(me.user);
    setProfiles(me.profiles);
  }, []);

  const login = useCallback(async (body: { email: string; password: string }) => {
    const me = await apiLogin(body);
    setUser(me.user);
    setProfiles(me.profiles);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setProfiles([]);
  }, []);

  return (
    <AuthContext.Provider value={{ loading, user, profiles, signup, login, logout, refresh, setProfiles }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
