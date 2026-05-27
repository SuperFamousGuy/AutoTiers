import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

const me = { user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] };

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext", () => {
  it("starts in loading state, then settles to anonymous on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
    vi.restoreAllMocks();
  });

  it("settles to authenticated when /me returns user", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user?.email).toBe("a@b.com");
    vi.restoreAllMocks();
  });
});
