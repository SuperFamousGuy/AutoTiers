import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";
import { server } from "@/tests/setup";
import generateResponseFixture from "@/tests/fixtures/generate-response.json";

const API_URL = "http://localhost:8000";

const USER = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  yahoo_fantasy_connected: false,
  google_subject: null,
  last_active_profile_id: "p1",
  has_password: true,
  email_verified: true,
  password_changed_at: null,
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
  // New dict format: per-position overrides keyed by position string.
  rules_json: {
    RB: [{ name: "RB Committee Penalty", enabled: false, weight: 1.0 }],
  },
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
  rules_json: {},
};

// Profile whose settings carry custom tier-label overrides. Drives the
// save → reload round-trip coverage for issue #169: the inputs must show the
// stored overrides on load, and an edited label must survive autosave + reload.
// tier_labels is keyed by tier number; JSON serializes the keys as strings.
const PROFILE_WITH_TIER_LABELS = {
  id: "p1",
  name: "PPR 12-team",
  settings_json: {
    ...PROFILE_ONE.settings_json,
    tier_labels: { 1: "Studs", 3: "Fills" },
  },
  rules_json: PROFILE_ONE.rules_json,
};

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
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
          rules_json: {},
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

  it("opens Manage profiles from the mobile hamburger menu (#499)", async () => {
    // The desktop ProfilePicker lives in a `hidden lg:flex` container, so on
    // narrow viewports profile management is only reachable via the always-present
    // hamburger menu's MobileProfileMenuItems. Clicking its "Manage Profiles…"
    // entry must open the same ManageProfilesDialog the desktop picker opens.
    mockAuthenticated();
    renderApp();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));

    // The mobile menu item (distinct from the desktop ProfilePicker's item) fires
    // the onManage handler App wires straight to setManageOpen.
    await user.click(screen.getByRole("menuitem", { name: /Manage Profiles/i }));

    // The dialog opened — its rename controls are present.
    const renameButtons = await screen.findAllByRole("button", { name: /^rename$/i });
    expect(renameButtons.length).toBeGreaterThan(0);
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
    // p1 is the active profile here, so the confirm copy names that consequence.
    await user.click(screen.getByRole("button", { name: /delete active profile/i }));

    await waitFor(() => expect(deletedId).toBe("p1"));
  });

  it("deleting the active profile clears the tier list and disables Generate (#626)", async () => {
    mockAuthenticated();
    server.use(
      http.delete(`${API_URL}/api/profiles/:id`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Generate a tier list for the active profile.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    const tiersPanel = screen.getByRole("tabpanel", { name: "Tiers" });
    await waitFor(() => expect(within(tiersPanel).getByText("Ja'Marr Chase")).toBeInTheDocument());

    // Delete the active profile via Manage profiles (two-click delete + confirm).
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Manage profiles/i }));
    const deleteIcons = await screen.findAllByRole("button", { name: /delete PPR 12-team/i });
    await user.click(deleteIcons[0]);
    // For the active profile, ManageProfilesDialog labels the confirm button
    // "Delete active profile" (not the generic "Confirm Delete").
    await user.click(await screen.findByRole("button", { name: /delete active profile/i }));

    // Close the modal so the (previously aria-hidden) main panels are queryable.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("Manage Profiles")).not.toBeInTheDocument());

    // The picker now shows no active profile.
    expect(screen.getByRole("button", { name: /No profile/i })).toBeInTheDocument();

    // The orphaned tiers must be cleared — the Tiers panel returns to its empty state.
    await waitFor(() => {
      const panel = screen.getByRole("tabpanel", { name: "Tiers" });
      expect(within(panel).getByText(/Click Generate to build your tier list\./i)).toBeInTheDocument();
    });
    expect(within(screen.getByRole("tabpanel", { name: "Tiers" })).queryByText("Ja'Marr Chase")).not.toBeInTheDocument();

    // Generate is disabled: profiles still exist (p2) but none is active.
    expect(screen.getByRole("button", { name: /^generate$/i })).toBeDisabled();
  });

  it("Undo button appears after a save lands and rewinds to the prior save point", async () => {
    mockAuthenticated();
    // Track the most recent payload sent to the server.
    let lastPatchPayload: { rules_json?: Record<string, Array<{ name: string; enabled: boolean; weight: number }>> } = {};
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
    expect(screen.queryByRole("button", { name: /undo last change/i })).not.toBeInTheDocument();

    // Toggle the first switch and wait for the autosave PATCH to land.
    await user.click(screen.getAllByRole("switch")[0]);
    await waitFor(
      () => expect(lastPatchPayload.rules_json).toBeDefined(),
      { timeout: 3000 },
    );

    // Now history has 2 entries → Undo button appears, with an explicit
    // accessible name + tooltip describing its scope (#694).
    const undoButton = await screen.findByRole("button", { name: /undo last change/i });
    expect(undoButton).toHaveAttribute(
      "title",
      "Revert settings and rules to the previous saved version",
    );

    // Click Undo — rewinds to the initial save point.
    await user.click(undoButton);
    await waitFor(() => {
      const restored = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));
      expect(restored).toEqual(initialState);
    });

    // A success toast confirms the (otherwise silent) revert (#694).
    expect(await screen.findByText(/reverted to previous settings/i)).toBeInTheDocument();

    // After Undo, history is back to 1 entry → button disappears.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /undo last change/i })).not.toBeInTheDocument();
    });
  });

  it("Undo shows an error toast and does not diverge from server state when the PATCH fails", async () => {
    mockAuthenticated();
    // First PATCH (the autosave that creates the 2nd history entry) succeeds;
    // the second PATCH (the undo) fails, so the server keeps the edited tip.
    let patchCount = 0;
    let lastPatchPayload: { rules_json?: Record<string, Array<{ name: string; enabled: boolean; weight: number }>> } = {};
    server.use(
      http.patch(`${API_URL}/api/profiles/:id`, async ({ request }) => {
        patchCount += 1;
        if (patchCount >= 2) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        lastPatchPayload = (await request.json()) as typeof lastPatchPayload;
        return HttpResponse.json({ ...PROFILE_ONE, ...lastPatchPayload });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Target Share Premium")).toBeInTheDocument());

    // Toggle the first switch and wait for the autosave PATCH to land, so the
    // Undo button appears. Capture the post-edit switch state — the state the
    // failed undo must NOT drift away from.
    await user.click(screen.getAllByRole("switch")[0]);
    await waitFor(() => expect(lastPatchPayload.rules_json).toBeDefined(), { timeout: 3000 });
    const undoButton = await screen.findByRole("button", { name: /undo last change/i });
    const editedState = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));

    // Click Undo — the PATCH fails.
    await user.click(undoButton);

    // An error toast names the failure...
    expect(await screen.findByText(/couldn't undo/i)).toBeInTheDocument();

    // ...and local state is rolled back to the server-truth (post-edit) snapshot,
    // not left showing the un-persisted revert (#694).
    await waitFor(() => {
      const current = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));
      expect(current).toEqual(editedState);
    });
    // History was restored, so the Undo button is still available to retry.
    expect(screen.getByRole("button", { name: /undo last change/i })).toBeInTheDocument();
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

  // Regression: clicking outside the LinkedAccounts dialog (overlay/outside click) must
  // restore body.style.pointerEvents so the page is interactive again.
  //
  // Root cause: two separate @radix-ui/react-dismissable-layer module instances existed
  // (v1.1.11 used by react-menu, v1.1.12 used by react-dialog), creating two independent
  // DismissableLayerContext singletons with separate `originalBodyPointerEvents` globals.
  // When the hamburger menu closed and the LinkedAccounts dialog opened in the same update,
  // the menu's DismissableLayer (1.1.11 context) had set body.style.pointerEvents="none" and
  // its cleanup correctly restored it. The dialog's DismissableLayer (1.1.12 context) then
  // set body.style.pointerEvents="none" again, storing "" as the original value. On outside
  // click, the 1.1.12 cleanup ran but checked its own context's size (which was 1) and
  // restored correctly — HOWEVER the 1.1.11 cleanup also ran when the menu dismounted and
  // because there were two independent counters, the overall state was inconsistent.
  // Fix: add "@radix-ui/react-dismissable-layer": "1.1.12" and
  // "@radix-ui/react-focus-guards": "1.1.4" to package.json overrides so a single
  // module instance (and a single DismissableLayerContext) is shared across all consumers.
  it("page is interactive after closing LinkedAccounts dialog via outside click", async () => {
    mockAuthenticated();
    renderApp();
    const user = userEvent.setup();

    // Dismiss the onboarding tour if present (it auto-starts in tests because localStorage
    // is clean; it renders as role="dialog" which would interfere with our assertions).
    const skipBtn = await screen.findByRole("button", { name: /skip/i }).catch(() => null);
    if (skipBtn) await user.click(skipBtn);

    // Open the hamburger menu (this sets body.style.pointerEvents="none" via DismissableLayer).
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));

    // Click "Connect Your League" — closes the dropdown, opens the dialog.
    await user.click(screen.getByRole("menuitem", { name: /connect your league/i }));

    // The LinkedAccounts dialog title is the discriminator (the tour uses a different label).
    const dialogTitle = await screen.findByText(/^connect your league$/i);
    expect(dialogTitle).toBeInTheDocument();

    // At this point, the dialog's DismissableLayer has set body.style.pointerEvents="none".
    expect(document.body.style.pointerEvents).toBe("none");

    // Wait for the DismissableLayer's setTimeout(0) listener registration to fire so that
    // the pointerdown listener on document is active before we dispatch events.
    await new Promise((r) => setTimeout(r, 0));

    // Simulate clicking outside the dialog content. We use fireEvent (not userEvent) because
    // userEvent refuses pointer interactions when body.style.pointerEvents is "none".
    // react-dialog >=1.1.17 sets deferPointerDownOutside on its DismissableLayer, so a
    // primary-button (button 0) pointerdown only *arms* the outside dismiss and defers the
    // actual close to the following click event — matching a real browser's
    // pointerdown -> pointerup -> click sequence. We must dispatch the click too.
    fireEvent.pointerDown(document.body);
    fireEvent.pointerUp(document.body);
    fireEvent.click(document.body);

    // The dialog should close — "Connect Your League" title leaves the DOM.
    await waitFor(() => expect(screen.queryByText(/^connect your league$/i)).not.toBeInTheDocument());

    // body.style.pointerEvents must be restored — the page must be interactive again.
    expect(document.body.style.pointerEvents).not.toBe("none");
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

  it("sends qb_starters: 2 in the generate request when the Superflex toggle is on (#724)", async () => {
    mockAuthenticated([PROFILE_ONE]);

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

    const user = userEvent.setup();
    const superflex = screen.getByRole("switch", { name: "Superflex / 2-QB league" });
    expect(superflex).not.toBeChecked();
    await user.click(superflex);
    expect(superflex).toBeChecked();

    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() => expect(generateBody.qb_starters).toBe(2));
  });

  it("omits/defaults qb_starters to single-QB when the Superflex toggle is off (#724)", async () => {
    mockAuthenticated([PROFILE_ONE]);

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

    // PROFILE_ONE's settings_json carries no qb_starters, so the toggle stays off
    // and the request must not request superflex math.
    expect(screen.getByRole("switch", { name: "Superflex / 2-QB league" })).not.toBeChecked();

    await userEvent.setup().click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() => expect(generateBody.qb_starters).not.toBe(2));
  });

  it("persists the Superflex toggle into the profile settings autosave (#724)", async () => {
    mockAuthenticated([PROFILE_ONE]);

    let lastPatchSettings: Record<string, unknown> | undefined;
    server.use(
      http.patch(`${API_URL}/api/profiles/:id`, async ({ params, request }) => {
        const body = (await request.json()) as { settings_json?: Record<string, unknown> };
        lastPatchSettings = body.settings_json;
        return HttpResponse.json({
          id: params.id,
          name: PROFILE_ONE.name,
          settings_json: body.settings_json ?? PROFILE_ONE.settings_json,
          rules_json: PROFILE_ONE.rules_json,
          linked_league: null,
        });
      }),
    );

    renderApp();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    await userEvent.setup().click(screen.getByRole("switch", { name: "Superflex / 2-QB league" }));

    // Autosave PATCHes the full settings_json, which must carry qb_starters: 2.
    await waitFor(() => expect(lastPatchSettings?.qb_starters).toBe(2), { timeout: 3000 });
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

  it("switching profiles resets mobile panel to Settings", async () => {
    mockAuthenticated();
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());

    // Manually navigate to the Rules tab
    await user.click(screen.getByRole("tab", { name: "Rules" }));
    expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "true");

    // Switch profiles
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());

    // After profile switch, Settings tab should be active
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "false");
  });

  it("clears the prior profile's generate result on profile switch (issue #238)", async () => {
    mockAuthenticated();
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Generate on profile 1 — default /api/generate handler returns the fixture.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument());

    // Switch to profile 2 — the prior result must be cleared, not lingered.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());

    // Tiers panel shows the empty state; the stale player is gone.
    await waitFor(() =>
      expect(screen.getByText("Click Generate to build your tier list.")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Ja'Marr Chase")).not.toBeInTheDocument();
  });

  it("mobile auto-switch-to-Tiers still fires on the first generate after a profile switch (issue #238 AC#2)", async () => {
    mockAuthenticated();
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // First generate on profile 1 consumes the auto-switch guard → Tiers tab.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"),
    );

    // Switch profiles — re-arms the guard and clears the result (back to Settings).
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");

    // The first generate AFTER the switch must auto-switch to Tiers again.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"),
    );
  });

  it("'+ New profile' clears stale result and returns to Settings (issue #238 / #228)", async () => {
    mockAuthenticated([PROFILE_ONE]);
    server.use(
      http.post(`${API_URL}/api/profiles`, async ({ request }) => {
        const body = (await request.json()) as { name?: string };
        return HttpResponse.json({
          id: "p-new",
          name: body.name,
          settings_json: PROFILE_ONE.settings_json,
          rules_json: {},
        });
      }),
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Generate, then jump to Tiers (auto-switch) so we can prove the reset.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"),
    );

    // Create a new profile — result cleared, mobile panel back to Settings.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /\+ New profile/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Profile 2/i })).toBeInTheDocument());

    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() =>
      expect(screen.getByText("Click Generate to build your tier list.")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Ja'Marr Chase")).not.toBeInTheDocument();

    // #228 re-arm: the guard was reset on new-profile, so the FIRST generate
    // after creating the profile must auto-switch back to Tiers. Without
    // `hasAutoSwitchedToTiers.current = false` in handleNewProfile, the guard
    // would still be consumed from the pre-create generate and this would fail.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"),
    );
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
          rules_json?: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
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

    // Edit profile 1: toggle the first rule switch (RB Committee Penalty starts disabled in PROFILE_ONE).
    const switches = screen.getAllByRole("switch");
    await user.click(switches[0]);
    const editedState = screen.getAllByRole("switch").map((s) => s.getAttribute("data-state"));

    // Wait for autosave (800ms debounce) — Undo only appears after the save lands.
    await waitFor(
      () => expect(screen.getByRole("button", { name: /undo last change/i })).toBeInTheDocument(),
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

  it("clears the prior profile's generate result on profile switch (#238)", async () => {
    mockAuthenticated();
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Generate on profile 1 — the Tiers panel now shows the result.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    const tiersPanel = screen.getByRole("tabpanel", { name: "Tiers" });
    await waitFor(() => expect(within(tiersPanel).getByText("Ja'Marr Chase")).toBeInTheDocument());
    // The empty-state copy is gone while a result is shown.
    expect(within(tiersPanel).queryByText(/Click Generate to build your tier list\./i)).not.toBeInTheDocument();

    // Switch to profile 2.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());

    // The Tiers panel must return to its empty state — NOT the prior profile's tiers.
    // This assertion fails if generate.reset() is removed from handleSelectProfile.
    await waitFor(() => {
      const panel = screen.getByRole("tabpanel", { name: "Tiers" });
      expect(within(panel).getByText(/Click Generate to build your tier list\./i)).toBeInTheDocument();
    });
    expect(within(screen.getByRole("tabpanel", { name: "Tiers" })).queryByText("Ja'Marr Chase")).not.toBeInTheDocument();
  });

  it("re-arms mobile auto-switch-to-Tiers on the first generate after a profile switch (#238)", async () => {
    mockAuthenticated();
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
      // Each generate returns a fresh object reference so the auto-switch effect re-fires.
      http.post(`${API_URL}/api/generate`, () => HttpResponse.json({ ...generateResponseFixture })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // First generate on profile 1 — auto-switches to Tiers.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"));

    // Switch profile — returns to Settings, clears result, re-arms the guard.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");

    // First generate AFTER the switch must auto-switch to Tiers again (guard re-armed).
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true"));
  });

  it("clears the prior profile's generate result when creating a new profile (#238 + #228)", async () => {
    mockAuthenticated([PROFILE_ONE]);
    server.use(
      http.post(`${API_URL}/api/profiles`, async ({ request }) => {
        const body = (await request.json()) as { name?: string };
        return HttpResponse.json({
          id: "p-new",
          name: body.name,
          settings_json: PROFILE_ONE.settings_json,
          rules_json: {},
        });
      }),
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Generate on the current profile.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() =>
      expect(within(screen.getByRole("tabpanel", { name: "Tiers" })).getByText("Ja'Marr Chase")).toBeInTheDocument(),
    );

    // Create a new profile.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /\+ New profile/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Profile 2/i })).toBeInTheDocument());

    // New profile starts from the Tiers empty state and the mobile view returns to Settings.
    await waitFor(() => {
      const panel = screen.getByRole("tabpanel", { name: "Tiers" });
      expect(within(panel).getByText(/Click Generate to build your tier list\./i)).toBeInTheDocument();
    });
    expect(within(screen.getByRole("tabpanel", { name: "Tiers" })).queryByText("Ja'Marr Chase")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
  });

  it("discards a stale in-flight generate that resolves after a profile switch (#283)", async () => {
    // Regression for the race raised in PR #283 review. A generate fired for
    // profile 1 can still be in flight when the user switches to profile 2.
    // `generate.reset()` (called in handleSelectProfile) does more than clear the
    // *displayed* result: in TanStack Query v5 it detaches this observer from the
    // running mutation, so when the late POST /api/generate response resolves it
    // is dropped rather than written back into `generate.data`. This test locks
    // in that behaviour — without the reset() the prior profile's tiers would
    // reappear under the new profile.
    mockAuthenticated();
    let releaseGenerate: () => void = () => {};
    const generateGate = new Promise<void>((resolve) => {
      releaseGenerate = resolve;
    });
    server.use(
      http.post(`${API_URL}/api/profiles/:id/activate`, () => new HttpResponse(null, { status: 204 })),
      // Hold the response open until the test releases it — simulating a generate
      // still in flight at the moment the user switches profiles.
      http.post(`${API_URL}/api/generate`, async () => {
        await generateGate;
        return HttpResponse.json({ ...generateResponseFixture });
      }),
    );

    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    // Kick off a generate on profile 1 that will not resolve yet.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    // Switch to profile 2 while that generate is still in flight.
    await user.click(screen.getByRole("button", { name: /PPR 12-team/i }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Standard Keeper/i })).toBeInTheDocument());

    // Now let the stale request resolve — its payload lands under profile 2.
    releaseGenerate();

    // The Tiers panel must stay in its empty state; the stale tiers must NOT appear.
    await waitFor(() => {
      const panel = screen.getByRole("tabpanel", { name: "Tiers" });
      expect(within(panel).getByText(/Click Generate to build your tier list\./i)).toBeInTheDocument();
    });
    // Give the resolved promise an extra tick to (wrongly) repopulate, then confirm it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(
      within(screen.getByRole("tabpanel", { name: "Tiers" })).queryByText("Ja'Marr Chase"),
    ).not.toBeInTheDocument();
  });

  it("shows stored tier_labels overrides in the Tier Labels inputs on profile load (#169)", async () => {
    mockAuthenticated([PROFILE_WITH_TIER_LABELS]);
    renderApp();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument(),
    );

    // The Tier Labels section is open by default; the stored overrides populate
    // their inputs while untouched tiers stay empty (showing the placeholder).
    await waitFor(() =>
      expect(screen.getByLabelText("Tier 1 label")).toHaveValue("Studs"),
    );
    expect(screen.getByLabelText("Tier 3 label")).toHaveValue("Fills");
    expect(screen.getByLabelText("Tier 2 label")).toHaveValue("");
  });

  it("an edited tier label round-trips through autosave and survives reload (#169)", async () => {
    // Server-side store that PATCH mutates and /me reads back, so a full remount
    // ("reload") re-hydrates from what was actually persisted — not from a stale
    // /me snapshot.
    let stored = PROFILE_WITH_TIER_LABELS;
    // Capture the profile id the autosave PATCHes so the round-trip assertion
    // fails if it ever targets the wrong profile (the handler matches any :id).
    let patchedId: string | undefined;
    server.use(
      http.get(`${API_URL}/api/auth/me`, () =>
        HttpResponse.json({ user: USER, profiles: [stored] }),
      ),
      http.patch(`${API_URL}/api/profiles/:id`, async ({ request, params }) => {
        patchedId = params.id as string;
        const body = (await request.json()) as {
          settings_json?: Record<string, unknown>;
          rules_json?: Record<string, unknown>;
        };
        stored = {
          ...stored,
          settings_json: (body.settings_json ?? stored.settings_json) as typeof stored.settings_json,
          rules_json: (body.rules_json ?? stored.rules_json) as typeof stored.rules_json,
        };
        return HttpResponse.json(stored);
      }),
    );

    const { unmount } = renderApp();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument(),
    );
    const tier1 = await screen.findByLabelText("Tier 1 label");
    await waitFor(() => expect(tier1).toHaveValue("Studs"));

    // Edit Tier 1's label, then blur to commit the trimmed value. (Avoid the
    // default "Elite" — handleTierLabelBlur treats a value equal to the default
    // as a reset, which would delete the override instead of persisting it.)
    await user.clear(tier1);
    await user.type(tier1, "Cornerstones");
    await user.tab();

    // Autosave (800ms debounce) persists the new label to the server store.
    await waitFor(
      () =>
        expect(
          (stored.settings_json.tier_labels as Record<string, string>)["1"],
        ).toBe("Cornerstones"),
      { timeout: 3000 },
    );
    // Autosave must target this profile, not some other id.
    expect(patchedId).toBe("p1");
    // The untouched override rides along in the same payload, unchanged.
    expect((stored.settings_json.tier_labels as Record<string, string>)["3"]).toBe("Fills");

    // Reload: unmount and re-render. /me now serves the persisted profile.
    unmount();
    renderApp();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Tier 1 label")).toHaveValue("Cornerstones"),
    );
    expect(screen.getByLabelText("Tier 3 label")).toHaveValue("Fills");
  });
});
