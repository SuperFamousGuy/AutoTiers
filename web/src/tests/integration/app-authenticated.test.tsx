import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { server } from "@/tests/setup";

const API_URL = "http://localhost:8000";

const USER = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  google_subject: null,
  last_active_profile_id: "p1",
};

const PROFILE_ONE = {
  id: "p1",
  name: "PPR 12-team",
  settings_json: {
    scoring_format: "ppr",
    league_size: 12,
    draft_rounds: 15,
    qb_td_points: 4,
    bonus_100yd_rushing: false,
    bonus_100yd_receiving: false,
    bonus_first_downs: false,
    weights: { prior: 30, consensus: 70 },
  },
  rules_json: [
    { name: "Target Share Premium", enabled: false, weight: 1.0 },
  ],
};

const PROFILE_TWO = {
  id: "p2",
  name: "Standard Keeper",
  settings_json: {
    scoring_format: "standard",
    league_size: 10,
    draft_rounds: 16,
    qb_td_points: 6,
    bonus_100yd_rushing: false,
    bonus_100yd_receiving: false,
    bonus_first_downs: false,
    weights: { prior: 50, consensus: 50 },
  },
  rules_json: [],
};

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function mockAuthenticated(profiles = [PROFILE_ONE, PROFILE_TWO]) {
  server.use(
    http.get(`${API_URL}/api/auth/me`, () =>
      HttpResponse.json({ user: USER, profiles }),
    ),
  );
}

describe("App (authenticated integration)", () => {
  it("hydrates the active profile's settings + rules on load", async () => {
    mockAuthenticated();
    renderApp();

    // ProfilePicker appears showing the active profile name
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument();
    });

    // Rules load; the user-customized rule reflects the profile (Target Share Premium disabled)
    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });
  });

  it("shows the hamburger user-email row and Log out item when authenticated", async () => {
    mockAuthenticated();
    renderApp();

    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));

    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
  });

  it("calls /api/auth/logout when Log out is clicked", async () => {
    mockAuthenticated();
    let logoutCalled = false;
    server.use(
      http.post(`${API_URL}/api/auth/logout`, () => {
        logoutCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));
    await user.click(screen.getByRole("menuitem", { name: /log out/i }));

    await waitFor(() => expect(logoutCalled).toBe(true));
  });

  it("switching profiles calls POST /activate on the picked profile", async () => {
    mockAuthenticated();
    let activatedId: string | null = null;
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, ({ params }) => {
        activatedId = params.id as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));

    await waitFor(() => expect(activatedId).toBe("p2"));
  });

  it("'+ New profile' creates a profile via POST /api/profiles", async () => {
    mockAuthenticated([PROFILE_ONE]);
    let createBody: { name?: string } = {};
    server.use(
      http.post(`${API_URL}/api/profiles`, async ({ request }) => {
        createBody = (await request.json()) as { name?: string };
        // Echo back the full settings_json so hydration doesn't blow up
        // on the missing `weights` field.
        return HttpResponse.json({
          id: "p-new",
          name: createBody.name,
          settings_json: PROFILE_ONE.settings_json,
          rules_json: [],
        });
      }),
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /\+ New profile/i }));

    await waitFor(() => expect(createBody.name).toBe("Profile 2"));
  });

  it("rename via Manage profiles PATCHes the profile name", async () => {
    mockAuthenticated();
    let patchBody: { name?: string } = {};
    let patchedId: string | null = null;
    server.use(
      http.patch(`${API_URL}/api/profiles/:id`, async ({ params, request }) => {
        patchedId = params.id as string;
        patchBody = (await request.json()) as { name?: string };
        return HttpResponse.json({ ...PROFILE_ONE, name: patchBody.name });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Manage profiles/i }));

    // Inside the dialog, rename the first profile
    const renameButtons = await screen.findAllByRole("button", { name: /^rename$/i });
    await user.click(renameButtons[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "Renamed Profile");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patchedId).toBe("p1");
      expect(patchBody.name).toBe("Renamed Profile");
    });
  });

  it("delete via Manage profiles calls DELETE on the profile", async () => {
    mockAuthenticated();
    let deletedId: string | null = null;
    server.use(
      http.delete(`${API_URL}/api/profiles/:id`, ({ params }) => {
        deletedId = params.id as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Manage profiles/i }));

    // Two-click delete
    const deleteIcons = await screen.findAllByRole("button", { name: /delete PPR 12-team/i });
    await user.click(deleteIcons[0]);
    await user.click(screen.getByRole("button", { name: /confirm delete/i }));

    await waitFor(() => expect(deletedId).toBe("p1"));
  });

  it("Undo button appears after a save lands and rewinds to the prior save point", async () => {
    mockAuthenticated();
    // Track the most recent payload sent to the server.
    let lastPatchPayload: { rules_json?: Array<{ name: string; enabled: boolean; weight: number }> } = {};
    server.use(
      http.patch(`${API_URL}/api/profiles/:id`, async ({ request }) => {
        lastPatchPayload = (await request.json()) as typeof lastPatchPayload;
        return HttpResponse.json({ ...PROFILE_ONE, ...lastPatchPayload });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Target Share Premium")).toBeInTheDocument());

    // Capture the initial rendered switch state.
    const initialState = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));

    // No save has landed yet → only 1 entry in history → Undo not shown.
    expect(screen.queryByRole("button", { name: /^undo$/i })).not.toBeInTheDocument();

    // Toggle the first switch and wait for the autosave PATCH to land.
    await user.click(screen.getAllByRole("switch")[0]);
    await waitFor(
      () => expect(lastPatchPayload.rules_json).toBeDefined(),
      { timeout: 3000 },
    );

    // Now history has 2 entries → Undo button appears.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^undo$/i })).toBeInTheDocument();
    });

    // Click Undo — rewinds to the initial save point.
    await user.click(screen.getByRole("button", { name: /^undo$/i }));
    await waitFor(() => {
      const restored = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));
      expect(restored).toEqual(initialState);
    });

    // After Undo, history is back to 1 entry → button disappears.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /^undo$/i })).not.toBeInTheDocument();
    });
  });

  it("opens Linked accounts dialog from the hamburger menu", async () => {
    mockAuthenticated();
    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));
    await user.click(screen.getByRole("menuitem", { name: /connect your league/i }));
    expect(await screen.findByText(/^connect your league$/i)).toBeInTheDocument();
  });

  it("includes keepers and league_adp in the generate request when active profile is linked", async () => {
    const linkedProfile = {
      ...PROFILE_ONE,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [
          { player_name: "Justin Jefferson", position: "WR", team: "MIN" },
        ],
        adp_json: { "Justin Jefferson": 1.0 },
        last_synced_at: "2026-01-01",
      },
    };
    mockAuthenticated([linkedProfile]);

    let generateBody: Record<string, unknown> = {};
    server.use(
      http.post(`${API_URL}/api/generate`, async ({ request }) => {
        generateBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ players: [], total: 0, data_as_of: null });
      }),
    );

    renderApp();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    const generateBtn = screen.getByRole("button", { name: /generate/i });
    await userEvent.setup().click(generateBtn);

    await waitFor(() => {
      expect(generateBody.keepers).toEqual(["Justin Jefferson"]);
      expect(generateBody.league_adp).toEqual({ "Justin Jefferson": 1.0 });
    });
  });

  it("auto-opens Linked accounts dialog with error when ?linking_error is present", async () => {
    mockAuthenticated();
    window.history.replaceState({}, "", "/?linking_error=already_linked_elsewhere");
    renderApp();
    await waitFor(() =>
      expect(screen.getByText(/already linked to a different AutoTiers account/i)).toBeInTheDocument(),
    );
    // URL param is stripped.
    expect(window.location.search).toBe("");
  });

  it("auto-opens Linked accounts dialog with session-lost message when ?linking_error=session_lost", async () => {
    mockAuthenticated();
    window.history.replaceState({}, "", "/?linking_error=session_lost");
    renderApp();
    await waitFor(() =>
      expect(screen.getByText(/sign-in session was lost/i)).toBeInTheDocument(),
    );
    expect(window.location.search).toBe("");
  });

  it("autosave updates AuthContext profiles so switching away and back preserves edits", async () => {
    // Bug regression: autosave PATCHed the server but discarded the returned
    // profile, so local `profiles` stayed stale. Switching profiles then
    // re-hydrated from the original /me snapshot — clobbering recent edits.
    mockAuthenticated();
    server.use(
      http.patch(`${API_URL}/api/profiles/:id`, async ({ params, request }) => {
        const body = (await request.json()) as {
          settings_json?: Record<string, unknown>;
          rules_json?: Array<{ name: string; enabled: boolean; weight: number }>;
        };
        const base = (params.id as string) === "p1" ? PROFILE_ONE : PROFILE_TWO;
        return HttpResponse.json({
          ...base,
          settings_json: body.settings_json ?? base.settings_json,
          rules_json: body.rules_json ?? base.rules_json,
        });
      }),
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Target Share Premium")).toBeInTheDocument());

    // Edit profile 1: toggle Target Share Premium on (it starts disabled in PROFILE_ONE).
    const switches = screen.getAllByRole("switch");
    await user.click(switches[0]);
    const editedState = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));

    // Wait for autosave (800ms debounce) — Undo only appears after the save lands.
    await waitFor(
      () => expect(screen.getByRole("button", { name: /^undo$/i })).toBeInTheDocument(),
      { timeout: 3000 },
    );

    // Switch to profile 2, then back to profile 1.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Standard Keeper/i }));
    await user.click(screen.getByRole("menuitem", { name: /PPR 12-team/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());

    // The edited state should be preserved — not clobbered by the original /me snapshot.
    await waitFor(() => {
      const restored = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));
      expect(restored).toEqual(editedState);
    });
  });
});
