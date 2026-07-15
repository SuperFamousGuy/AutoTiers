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

  // Monotonic sequence guard. The four async auth operations — refresh(),
  // login(), signup(), and logout() — each capture the id they were issued
  // with; only the response of the latest-issued of those four is allowed to
  // apply its result to the guarded state (user, profiles, loading). Without
  // this, concurrent calls race — the mount refresh() and a
  // post-email-verification refresh() fire back-to-back, and if the older
  // (pre-verification) /api/auth/me response resolves last it would silently
  // overwrite the just-verified state with stale "unverified" data (#713).
  //
  // login()/signup()/logout() must share the same counter: the mount refresh()
  // can still be in flight when the user logs in, and its stale (anonymous)
  // payload would otherwise clobber the just-logged-in state on resolution
  // (#725). Bumping the seq before the network call invalidates any in-flight
  // refresh(), and applyIfCurrent() drops a stale refresh() that resolves late.
  //
  // NOTE: the raw setProfiles setter exposed on the context is deliberately
  // NOT covered by this guard — it is a synchronous, caller-driven update (no
  // in-flight response to race), so callers own its ordering.
  const refreshSeq = useRef(0);

  // Run `apply` only if `seq` is still the latest-issued sequence — i.e. no
  // newer refresh()/login()/signup()/logout() has been issued since. A stale
  // in-flight call that resolves after a newer one is silently discarded.
  const applyIfCurrent = useCallback((seq: number, apply: () => void) => {
    if (seq === refreshSeq.current) apply();
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current;
    setLoading(true);
    try {
      const me = await getMe();
      applyIfCurrent(seq, () => {
        setUser(me?.user ?? null);
        setProfiles(me?.profiles ?? []);
      });
    } finally {
      // Always clear loading — getMe swallows 401 but a network/5xx
      // error would otherwise leave the app stuck in the loading state.
      // Only the latest call clears loading, so an early-resolving stale
      // call can't drop the spinner while the newest call is still in flight.
      applyIfCurrent(seq, () => setLoading(false));
    }
  }, [applyIfCurrent]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signup = useCallback(async (body: Parameters<AuthContextValue["signup"]>[0]) => {
    const seq = ++refreshSeq.current;
    try {
      const me = await apiSignup(body);
      applyIfCurrent(seq, () => {
        setUser(me.user);
        setProfiles(me.profiles);
      });
    } finally {
      // Bumping the seq above invalidated any in-flight mount refresh(), so its
      // loading-clear is now suppressed — clear loading here (if still current)
      // to avoid leaving the app stuck in the spinner (#725).
      applyIfCurrent(seq, () => setLoading(false));
    }
  }, [applyIfCurrent]);

  const login = useCallback(async (body: { email: string; password: string }) => {
    const seq = ++refreshSeq.current;
    try {
      const me = await apiLogin(body);
      applyIfCurrent(seq, () => {
        setUser(me.user);
        setProfiles(me.profiles);
      });
    } finally {
      applyIfCurrent(seq, () => setLoading(false));
    }
  }, [applyIfCurrent]);

  const logout = useCallback(async () => {
    const seq = ++refreshSeq.current;
    try {
      await apiLogout();
      applyIfCurrent(seq, () => {
        setUser(null);
        setProfiles([]);
      });
    } finally {
      applyIfCurrent(seq, () => setLoading(false));
    }
  }, [applyIfCurrent]);

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
