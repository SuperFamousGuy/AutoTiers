import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { getMe, login as apiLogin, logout as apiLogout, signup as apiSignup } from "@/api/auth";
import type { User, Profile } from "@/api/types";

interface AuthContextValue {
  loading: boolean;
  user: User | null;
  profiles: Profile[];
  signup: (body: { email: string; password: string; initial_settings?: Record<string, unknown>; initial_rules?: Array<Record<string, unknown>> }) => Promise<void>;
  login: (body: { email: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setProfiles: (next: Profile[]) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    const me = await getMe();
    setUser(me?.user ?? null);
    setProfiles(me?.profiles ?? []);
    setLoading(false);
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
