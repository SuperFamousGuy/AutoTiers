# Account Linking UX Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the account linking dialog's in-place content swap with a tabbed layout, rename "Linked Accounts" to "Connect Your League", add a Sleeper step indicator, gate ESPN private credentials behind a toggle, and show connected-state confirmation cards per platform tab.

**Architecture:** Four components are touched — `Header.tsx` (one-line rename), `SleeperConnectForm.tsx` (new `profile`/`onRefresh` props, step indicator, connected-state view, remove `onCancel`), `EspnConnectForm.tsx` (same shape as Sleeper plus public/private toggle buttons), and `LinkedAccountsDialog.tsx` (tab strip replaces `activeForm`; Google demoted to footer). `LinkedLeagueSection.tsx` becomes dead code and is deleted in Task 5. Tests are updated TDD-style alongside each component.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, vitest + @testing-library/react, shadcn/ui

---

## File Map

| File | Change |
|------|--------|
| `web/src/components/Header.tsx` | Line 37: text "Linked Accounts" → "Connect Your League" |
| `web/src/components/SleeperConnectForm.tsx` | New `profile: Profile` + `onRefresh` props; `onCancel` removed; `StepIndicator` sub-component; `SleeperConnectedState` sub-component |
| `web/src/components/EspnConnectForm.tsx` | New `profile: Profile` + `onRefresh` props; `onCancel` removed; two-button public/private toggle; `EspnConnectedState` sub-component |
| `web/src/components/LinkedAccountsDialog.tsx` | Full rewrite: `activeTab` state, tab strip, per-tab rendering, Google footer row |
| `web/src/components/LinkedLeagueSection.tsx` | **Delete** |
| `web/src/tests/components/SleeperConnectForm.test.tsx` | Update all `render` calls; add step indicator + connected state + Refresh/Disconnect tests |
| `web/src/tests/components/EspnConnectForm.test.tsx` | Update all `render` calls; replace checkbox with button tests; add connected state + Refresh/Disconnect tests |
| `web/src/tests/components/LinkedAccountsDialog.test.tsx` | Full rewrite for tab-based structure |
| `web/src/tests/components/LinkedLeagueSection.test.tsx` | **Delete** |

---

## Task 1: Rename "Linked Accounts" → "Connect Your League" in Header

**Files:**
- Modify: `web/src/components/Header.tsx:37`

- [ ] **Step 1: Apply the rename**

In `web/src/components/Header.tsx`, find this line:

```tsx
              <DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
                Linked Accounts
              </DropdownMenuItem>
```

Replace with:

```tsx
              <DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
                Connect Your League
              </DropdownMenuItem>
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

Expected: no output (no errors).

- [ ] **Step 3: Commit**

```bash
git -C /Users/karlkell/Code/AutoTiers add web/src/components/Header.tsx
git -C /Users/karlkell/Code/AutoTiers commit -m "feat(ux): rename 'Linked Accounts' menu item to 'Connect Your League'"
```

---

## Task 2: Update SleeperConnectForm

Replaces `profileId: string` + `onCancel` with `profile: Profile` + `onRefresh`. Adds a two-node `StepIndicator` above the form and a `SleeperConnectedState` view that renders when `profile.linked_league?.provider === "sleeper"`.

**Files:**
- Modify: `web/src/tests/components/SleeperConnectForm.test.tsx`
- Modify: `web/src/components/SleeperConnectForm.tsx`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `web/src/tests/components/SleeperConnectForm.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

const baseProfile: Profile = {
  id: "p1",
  name: "My",
  settings_json: {},
  rules_json: [],
  linked_league: null,
};

const sleeperLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "sleeper",
    league_id: "L1",
    league_metadata_json: { name: "Best League", season: 2026 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("SleeperConnectForm", () => {
  // --- connect flow ---

  it("lists leagues across current + previous season, then connects on confirm", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([{ id: "L0", name: "Old Dynasty", season: 2025 }]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L1",
        league_metadata_json: { name: "Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    expect(screen.getByText(/old dynasty/i)).toBeInTheDocument();
    expect(listSleeperLeagues).toHaveBeenCalledTimes(2);
    await u.selectOptions(screen.getByLabelText(/select your league/i), "L1");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L1", season: 2026,
    }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("connects with the SELECTED league's season, not always the current one", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: "L0", name: "Old Dynasty", season: 2025 }]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L0",
        league_metadata_json: { name: "Old Dynasty", season: 2025 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/old dynasty/i)).toBeInTheDocument());
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L0", season: 2025,
    }));
  });

  it("shows error when username not found", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new ApiError(404, "not found"))
      .mockRejectedValueOnce(new ApiError(404, "not found"));
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "ghost");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/couldn't find/i)).toBeInTheDocument());
  });

  it("upfront username step does NOT show the link-without-league button", () => {
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /link without a league/i })).not.toBeInTheDocument();
  });

  it("when zero leagues are found, surfaces a 'Link without a league' button that pre-links", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: null,
        league_metadata_json: null, keepers_json: null, adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "leagueless");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() =>
      expect(screen.getByText(/no sleeper leagues found/i)).toBeInTheDocument(),
    );
    await u.click(screen.getByRole("button", { name: /link without a league/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", { username: "leagueless" }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  // --- step indicator ---

  it("shows a step indicator on the username step", () => {
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByLabelText(/connection steps/i)).toBeInTheDocument();
  });

  it("'Wrong username?' link goes back to step 1 without clearing the username field", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([]);
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    await u.click(screen.getByText(/wrong username/i));
    const input = screen.getByLabelText(/sleeper username/i) as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("alice");
  });

  // --- connected state ---

  it("shows connected state card when profile.linked_league.provider === 'sleeper'", () => {
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    expect(screen.getByText(/connected!/i)).toBeInTheDocument();
    expect(screen.getByText("Best League")).toBeInTheDocument();
    expect(screen.queryByLabelText(/sleeper username/i)).not.toBeInTheDocument();
  });

  it("Refresh calls refreshLink then onRefresh", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Disconnect calls disconnectLink then onRefresh", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/SleeperConnectForm.test.tsx 2>&1 | tail -20
```

Expected: multiple failures — `profile` prop not found, `onRefresh` not found, `onCancel` still required, connected state elements missing.

- [ ] **Step 3: Rewrite the implementation**

Replace the entire contents of `web/src/components/SleeperConnectForm.tsx`:

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  listSleeperLeagues,
  connectSleeper,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { SleeperLeagueSummary, Profile } from "@/api/types";
import { currentSeason } from "@/lib/season";
import { cn } from "@/lib/utils";

interface Props {
  profile: Profile;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

function StepIndicator({ step }: { step: "username" | "league" }) {
  const atLeague = step === "league";
  return (
    <div className="flex items-center gap-1.5 mb-3 text-xs" aria-label="Connection steps">
      <div
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
          atLeague ? "bg-green-500 text-white" : "bg-primary text-primary-foreground",
        )}
      >
        {atLeague ? "✓" : "1"}
      </div>
      <span className={cn("text-xs font-medium", atLeague && "text-green-600")}>
        Find your account
      </span>
      <div className={cn("h-px flex-1", atLeague ? "bg-primary" : "bg-border")} />
      <div
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
          atLeague
            ? "bg-primary text-primary-foreground"
            : "border-2 border-border text-muted-foreground",
        )}
      >
        2
      </div>
      <span className={cn("text-xs", atLeague ? "font-medium" : "text-muted-foreground")}>
        Pick league
      </span>
    </div>
  );
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function SleeperConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    setBusy(true);
    try {
      await disconnectLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="rounded-lg border-2 border-green-500 bg-green-50/50 p-3">
        <div className="mb-1 flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500">
            <span className="text-[10px] font-bold text-white">✓</span>
          </div>
          <span className="text-sm font-bold text-green-700">Connected!</span>
        </div>
        <p className="text-sm font-medium">
          {linked.league_metadata_json?.name ?? "Account linked (no league)"}
        </p>
        <p className="text-xs text-muted-foreground">
          Sleeper{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
      </div>
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          aria-label="Disconnect Sleeper"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function SleeperConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [step, setStep] = useState<"username" | "league">("username");
  const [username, setUsername] = useState("");
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [chosenLeague, setChosenLeague] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const linked = profile.linked_league;
  if (linked?.provider === "sleeper") {
    return (
      <SleeperConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleContinue() {
    setError(null);
    setBusy(true);
    try {
      const seasons = [currentSeason(), currentSeason() - 1];
      const username_trimmed = username.trim();
      let userNotFound = false;
      const settled = await Promise.all(
        seasons.map(async (season) => {
          try {
            return await listSleeperLeagues(profile.id, username_trimmed, season);
          } catch (e) {
            if (e instanceof ApiError && e.status === 404) userNotFound = true;
            return [];
          }
        }),
      );
      if (userNotFound) {
        setError("We couldn't find that Sleeper username.");
        return;
      }
      const flat = settled.flat();
      const byId = new Map<string, SleeperLeagueSummary>();
      for (const l of flat) {
        const existing = byId.get(l.id);
        if (!existing || l.season > existing.season) byId.set(l.id, l);
      }
      const result = Array.from(byId.values()).sort((a, b) => b.season - a.season);
      if (result.length === 0) {
        setError(
          `No Sleeper leagues found for "${username_trimmed}" in ${seasons[1]} or ${seasons[0]}.`,
        );
        return;
      }
      setLeagues(result);
      setChosenLeague(result[0].id);
      setStep("league");
    } catch {
      setError("Couldn't reach Sleeper. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const chosen = leagues.find((l) => l.id === chosenLeague);
      const result = await connectSleeper(profile.id, {
        username: username.trim(),
        league_id: chosenLeague,
        season: chosen?.season ?? currentSeason(),
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkWithoutLeague() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectSleeper(profile.id, { username: username.trim() });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const noLeaguesFound = error !== null && error.includes("No Sleeper leagues");

  return (
    <div className="space-y-3">
      <StepIndicator step={step} />
      {error && (
        <div className="space-y-2">
          <p className="text-xs text-red-600">{error}</p>
          {noLeaguesFound && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !username.trim()}
              onClick={handleLinkWithoutLeague}
            >
              Link without a league
            </Button>
          )}
        </div>
      )}
      {step === "username" ? (
        <>
          <label className="block text-sm">
            <span>Sleeper Username</span>
            <input
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-label="Sleeper username"
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button size="sm" disabled={busy || !username.trim()} onClick={handleContinue}>
              Continue
            </Button>
          </div>
        </>
      ) : (
        <>
          <label className="block text-sm">
            <span>Select Your League</span>
            <select
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={chosenLeague}
              onChange={(e) => setChosenLeague(e.target.value)}
              aria-label="Select your league"
            >
              {leagues.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.season})
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center justify-between gap-2">
            <button
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => setStep("username")}
            >
              ← Wrong username?
            </button>
            <Button size="sm" disabled={busy} onClick={handleConnect}>
              Connect
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests — expect all green**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/SleeperConnectForm.test.tsx 2>&1 | tail -10
```

Expected: `Tests 11 passed (11)` (or similar count).

- [ ] **Step 5: Type-check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C /Users/karlkell/Code/AutoTiers add web/src/components/SleeperConnectForm.tsx web/src/tests/components/SleeperConnectForm.test.tsx
git -C /Users/karlkell/Code/AutoTiers commit -m "feat(ux): SleeperConnectForm — profile prop, step indicator, connected state"
```

---

## Task 3: Update EspnConnectForm

Same shape as Task 2. Replaces the checkbox with a two-button public/private toggle. Adds `EspnConnectedState` for when `profile.linked_league?.provider === "espn"`. `onCancel` removed.

**Files:**
- Modify: `web/src/tests/components/EspnConnectForm.test.tsx`
- Modify: `web/src/components/EspnConnectForm.tsx`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `web/src/tests/components/EspnConnectForm.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  connectEspn: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

const baseProfile: Profile = {
  id: "p1",
  name: "My",
  settings_json: {},
  rules_json: [],
  linked_league: null,
};

const espnLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "espn",
    league_id: "12345",
    league_metadata_json: { name: "ESPN Champs", season: 2026 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("EspnConnectForm", () => {
  it("connects public league without cookie fields", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<EspnConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345",
    })));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("Connect is disabled when league ID is empty in public mode", () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("Connect becomes enabled with cookies only in private mode (no league ID)", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/swid/i), "{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeEnabled();
  });

  it("reveals SWID + espn_s2 fields when Private League button is clicked", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    expect(screen.queryByLabelText(/swid/i)).not.toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    expect(await screen.findByLabelText(/swid/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/espn_s2/i)).toBeInTheDocument();
  });

  it("includes cookies in the body when private + all fields filled", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345", swid: "{abc-123}", espn_s2: "blob",
    })));
  });

  // --- connected state ---

  it("shows connected state card when profile.linked_league.provider === 'espn'", () => {
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    expect(screen.getByText(/connected!/i)).toBeInTheDocument();
    expect(screen.getByText("ESPN Champs")).toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });

  it("Refresh calls refreshLink then onRefresh", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Disconnect calls disconnectLink then onRefresh", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect espn/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/EspnConnectForm.test.tsx 2>&1 | tail -20
```

Expected: failures on `profile` prop, `onRefresh` prop, button-based private toggle, connected state.

- [ ] **Step 3: Rewrite the implementation**

Replace the entire contents of `web/src/components/EspnConnectForm.tsx`:

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectEspn,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import { currentSeason } from "@/lib/season";
import type { Profile } from "@/api/types";

interface Props {
  profile: Profile;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function EspnConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    setBusy(true);
    try {
      await disconnectLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="rounded-lg border-2 border-green-500 bg-green-50/50 p-3">
        <div className="mb-1 flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500">
            <span className="text-[10px] font-bold text-white">✓</span>
          </div>
          <span className="text-sm font-bold text-green-700">Connected!</span>
        </div>
        <p className="text-sm font-medium">
          {linked.league_metadata_json?.name ?? "Account linked (no league)"}
        </p>
        <p className="text-xs text-muted-foreground">
          ESPN{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
      </div>
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          aria-label="Disconnect ESPN"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function EspnConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [leagueId, setLeagueId] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [swid, setSwid] = useState("");
  const [espnS2, setEspnS2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const linked = profile.linked_league;
  if (linked?.provider === "espn") {
    return (
      <EspnConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const trimmedLeague = leagueId.trim();
      const result = await connectEspn(profile.id, {
        league_id: trimmedLeague || undefined,
        season: trimmedLeague ? currentSeason() : undefined,
        swid: isPrivate ? swid.trim() : undefined,
        espn_s2: isPrivate ? espnS2.trim() : undefined,
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // Public: must have leagueId.
  // Private: leagueId OR (both cookies filled) — allows pre-linking with cookies only.
  const connectDisabled =
    busy ||
    (!isPrivate && leagueId.trim() === "") ||
    (isPrivate && leagueId.trim() === "" && (swid.trim() === "" || espnS2.trim() === ""));

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* Public / Private toggle */}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant={isPrivate ? "outline" : "default"}
          aria-label="Public league"
          onClick={() => setIsPrivate(false)}
        >
          Public league
        </Button>
        <Button
          size="sm"
          variant={isPrivate ? "default" : "outline"}
          aria-label="Private league"
          onClick={() => setIsPrivate(true)}
        >
          Private league
        </Button>
      </div>

      {/* League ID */}
      <label className="block text-sm">
        <span>
          League ID{" "}
          {isPrivate && (
            <span className="text-xs text-muted-foreground">(optional if using cookies only)</span>
          )}
        </span>
        <input
          className="mt-1 block w-full rounded border px-2 py-1 text-sm"
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value)}
          aria-label="League ID"
          placeholder="e.g. 336041"
        />
      </label>
      {!isPrivate && (
        <p className="text-xs text-muted-foreground">
          Find it in your ESPN league URL:{" "}
          /fantasy/football/leagues/<strong>{leagueId || "336041"}</strong>
        </p>
      )}

      {/* Private credentials */}
      {isPrivate && (
        <div className="space-y-2 rounded border bg-muted/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium">🍪 Private credentials</span>
            <a
              href="https://chromewebstore.google.com/detail/gameday-bot/nkplmhgeegmlfpkiiakfjpmhbinibojc"
              target="_blank"
              rel="noreferrer"
              className="text-xs underline"
            >
              How to find these ↗
            </a>
          </div>
          <p className="text-xs text-muted-foreground">
            Use the{" "}
            <a
              href="https://chromewebstore.google.com/detail/gameday-bot/nkplmhgeegmlfpkiiakfjpmhbinibojc"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              GameDayBot
            </a>{" "}
            or{" "}
            <a
              href="https://www.pff.com/fantasy"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              PFF
            </a>{" "}
            browser extension to copy these values automatically, or find them manually via
            DevTools → Application → Cookies → fantasy.espn.com.
          </p>
          <label className="block text-xs">
            <span>SWID</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={swid}
              onChange={(e) => setSwid(e.target.value)}
              aria-label="SWID"
              placeholder="{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
            />
          </label>
          <label className="block text-xs">
            <span>espn_s2</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={espnS2}
              onChange={(e) => setEspnS2(e.target.value)}
              aria-label="espn_s2"
              placeholder="long opaque string"
            />
          </label>
        </div>
      )}

      <div className="flex justify-end">
        <Button size="sm" disabled={connectDisabled} onClick={handleConnect}>
          Connect
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests — expect all green**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/EspnConnectForm.test.tsx 2>&1 | tail -10
```

Expected: `Tests 8 passed (8)` (or similar count).

- [ ] **Step 5: Type-check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C /Users/karlkell/Code/AutoTiers add web/src/components/EspnConnectForm.tsx web/src/tests/components/EspnConnectForm.test.tsx
git -C /Users/karlkell/Code/AutoTiers commit -m "feat(ux): EspnConnectForm — profile prop, public/private toggle, connected state"
```

---

## Task 4: Rewrite LinkedAccountsDialog

Replaces `activeForm` + `LinkedLeagueSection` with a persistent platform tab strip. Google moves to a footer row. `SleeperConnectForm` and `EspnConnectForm` are rendered directly inside their tabs.

**Key behavior changes:**
- `activeTab` defaults to `"sleeper"`, resets to `"sleeper"` on dialog close
- Sleeper/ESPN tabs require `activeProfile` — show "Select a profile" if null
- Yahoo tab shows OAuth button regardless of `activeProfile` (no profile needed for OAuth redirect)
- NFL/CBS tabs are disabled with "coming soon" text
- Google footer shows "Link" or "Unlink" based on `user.google_subject`

**Files:**
- Modify: `web/src/tests/components/LinkedAccountsDialog.test.tsx`
- Modify: `web/src/components/LinkedAccountsDialog.tsx`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `web/src/tests/components/LinkedAccountsDialog.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import type { User, Profile } from "@/api/types";

vi.mock("@/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/api/auth")>("@/api/auth");
  return {
    ...actual,
    unlinkGoogle: vi.fn(),
    googleAuthorizeUrl: () => "http://localhost:8000/api/auth/google/authorize",
    yahooAuthorizeUrl: () => "http://localhost:8000/api/auth/yahoo/authorize",
  };
});

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
  connectEspn: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

const baseUser: User = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  google_subject: null,
  last_active_profile_id: null,
};

const activeProfile: Profile = {
  id: "p1",
  name: "My",
  settings_json: {},
  rules_json: [],
  linked_league: null,
};

const noop = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LinkedAccountsDialog", () => {
  it("renders with title 'Connect Your League'", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText("Connect Your League")).toBeInTheDocument();
  });

  it("renders a tab strip with all five platforms", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByRole("button", { name: /^sleeper$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^espn$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^yahoo$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^nfl fantasy$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^cbs$/i })).toBeInTheDocument();
  });

  it("default active tab is Sleeper — Sleeper username field is visible", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByLabelText(/sleeper username/i)).toBeInTheDocument();
  });

  it("clicking the ESPN tab shows the ESPN League ID field", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^espn$/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();
  });

  it("clicking the Yahoo tab shows the Yahoo OAuth button", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^yahoo$/i }));
    expect(await screen.findByRole("button", { name: /continue with yahoo/i })).toBeInTheDocument();
  });

  it("shows 'Select a profile' when Sleeper tab is active but no activeProfile is provided", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/select a profile/i)).toBeInTheDocument();
  });

  it("Google footer shows Link button when Google is not connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /^link google$/i })).toBeInTheDocument();
  });

  it("Google footer shows Unlink button when Google is connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /disconnect google/i })).toBeInTheDocument();
  });

  it("Unlink Google calls unlinkGoogle then onRefresh", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const refresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={refresh} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    await waitFor(() => expect(unlinkGoogle).toHaveBeenCalled());
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("shows the API error message when unlinkGoogle fails", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    const { ApiError } = await import("@/api/client");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "Cannot unlink last sign-in method"),
    );
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    expect(await screen.findByText(/last sign-in method/i)).toBeInTheDocument();
  });

  it("Link Google navigates to the authorize URL with intent=link", async () => {
    let assignedHref = "";
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, set href(v: string) { assignedHref = v; } },
    });
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^link google$/i }));
    expect(assignedHref).toContain("/api/auth/google/authorize");
    expect(assignedHref).toContain("intent=link");
    Object.defineProperty(window, "location", { writable: true, value: { href: "" } });
  });

  it("renders an initial error when provided", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop}
        initialError="This Google account is already linked to a different AutoTiers account." />,
    );
    expect(screen.getByText(/already linked/i)).toBeInTheDocument();
  });

  it("closing the dialog resets active tab to Sleeper", async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <LinkedAccountsDialog open={true} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^espn$/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();

    rerender(
      <LinkedAccountsDialog open={false} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    rerender(
      <LinkedAccountsDialog open={true} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    expect(await screen.findByLabelText(/sleeper username/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx 2>&1 | tail -20
```

Expected: failures on "Connect Your League" title, tab buttons, Google footer button names.

- [ ] **Step 3: Rewrite the implementation**

Replace the entire contents of `web/src/components/LinkedAccountsDialog.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle } from "@/api/auth";
import { ApiError } from "@/api/client";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import {
  GoogleIcon,
  YahooIcon,
  SleeperIcon,
  EspnIcon,
  NflFantasyIcon,
  CbsIcon,
} from "@/components/BrandIcons";
import { cn } from "@/lib/utils";
import type { User, Profile } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  onRefresh: () => Promise<void>;
  initialError: string | null;
  activeProfile?: Profile | null;
}

type PlatformTab = "sleeper" | "espn" | "yahoo" | "nfl" | "cbs";

const TABS: {
  id: PlatformTab;
  label: string;
  Icon: () => JSX.Element;
  comingSoon?: boolean;
}[] = [
  { id: "sleeper", label: "Sleeper", Icon: SleeperIcon },
  { id: "espn", label: "ESPN", Icon: EspnIcon },
  { id: "yahoo", label: "Yahoo", Icon: YahooIcon },
  { id: "nfl", label: "NFL Fantasy", Icon: NflFantasyIcon, comingSoon: true },
  { id: "cbs", label: "CBS", Icon: CbsIcon, comingSoon: true },
];

export function LinkedAccountsDialog({
  open,
  onOpenChange,
  user,
  onRefresh,
  initialError,
  activeProfile,
}: Props) {
  const [error, setError] = useState<string | null>(initialError);
  const [activeTab, setActiveTab] = useState<PlatformTab>("sleeper");
  const [googleBusy, setGoogleBusy] = useState(false);

  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  useEffect(() => {
    if (!open) setActiveTab("sleeper");
  }, [open]);

  async function handleGoogleDisconnect() {
    setError(null);
    setGoogleBusy(true);
    try {
      await unlinkGoogle();
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed. Please try again.");
    } finally {
      setGoogleBusy(false);
    }
  }

  function handleGoogleConnect() {
    window.location.href = `${googleAuthorizeUrl()}?intent=link`;
  }

  function handleYahooConnect() {
    window.location.href = `${yahooAuthorizeUrl()}?intent=link`;
  }

  function renderTabPanel() {
    // Sleeper and ESPN need an active profile for their API calls.
    if ((activeTab === "sleeper" || activeTab === "espn") && !activeProfile) {
      return (
        <p className="py-4 text-center text-xs text-muted-foreground">
          Select a profile above to connect a fantasy league.
        </p>
      );
    }

    switch (activeTab) {
      case "sleeper":
        return (
          <SleeperConnectForm
            profile={activeProfile!}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "espn":
        return (
          <EspnConnectForm
            profile={activeProfile!}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "yahoo":
        return (
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              Connect via Yahoo OAuth. We'll find your Yahoo Fantasy leagues automatically after
              you authorize.
            </p>
            <Button className="w-full" onClick={handleYahooConnect}>
              <YahooIcon /> Continue with Yahoo
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              You'll be redirected to Yahoo, then brought back here.
            </p>
          </div>
        );
      case "nfl":
      case "cbs": {
        const name = activeTab === "nfl" ? "NFL Fantasy" : "CBS Sports";
        return (
          <div className="space-y-1 py-6 text-center">
            <p className="text-sm font-medium">{name} — Coming Soon</p>
            <p className="text-xs text-muted-foreground">
              We're working on it. Check back next season.
            </p>
          </div>
        );
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0">
        <div className="px-6 pt-6 pb-4">
          <DialogTitle>Connect Your League</DialogTitle>
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>

        {/* Platform tab strip */}
        <div className="flex overflow-x-auto border-b border-border">
          {TABS.map(({ id, label, Icon, comingSoon }) => (
            <button
              key={id}
              aria-label={label}
              disabled={comingSoon}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-2.5 text-xs font-medium transition-colors",
                activeTab === id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
                comingSoon && "cursor-not-allowed opacity-40",
              )}
            >
              <Icon />
              {label}
              {comingSoon && <span className="ml-0.5 text-[10px] font-normal">(soon)</span>}
            </button>
          ))}
        </div>

        {/* Tab panel */}
        <div className="px-6 py-4">{renderTabPanel()}</div>

        {/* Google footer — sign-in only, no fantasy league */}
        <div className="flex items-center justify-between border-t border-border px-6 py-3">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <GoogleIcon />
            Google · Sign-in only, no fantasy league
          </span>
          {user.google_subject ? (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              disabled={googleBusy}
              aria-label="Disconnect Google"
              onClick={handleGoogleDisconnect}
            >
              Unlink
            </Button>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              aria-label="Link Google"
              onClick={handleGoogleConnect}
            >
              Link
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

**Note on `DialogContent className="gap-0 p-0"`:** The standard shadcn `DialogContent` has padding built in. We're overriding with `p-0` to control padding per section (header, tab strip, panel, footer). Check `web/src/components/ui/dialog.tsx` — if the component doesn't accept `className` for padding override, adjust accordingly.

- [ ] **Step 4: Run the LinkedAccountsDialog tests**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx 2>&1 | tail -15
```

Expected: `Tests 13 passed (13)` (or similar count). If any test fails, check the accessible name of buttons — `aria-label` values in the implementation must match what the tests query.

- [ ] **Step 5: Run the broader component test suite**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/ 2>&1 | tail -10
```

Expected: all tests pass. This catches regressions in any component that imports `LinkedAccountsDialog`, `SleeperConnectForm`, or `EspnConnectForm`.

- [ ] **Step 6: Type-check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

Expected: no output. Common errors to watch for: `cn` not imported, `JSX.Element` return type on TABS array, `activeProfile!` non-null assertion on null/undefined.

- [ ] **Step 7: Commit**

```bash
git -C /Users/karlkell/Code/AutoTiers add \
  web/src/components/LinkedAccountsDialog.tsx \
  web/src/tests/components/LinkedAccountsDialog.test.tsx
git -C /Users/karlkell/Code/AutoTiers commit -m "feat(ux): LinkedAccountsDialog — tab strip, Google footer, 'Connect Your League'"
```

---

## Task 5: Delete LinkedLeagueSection

`LinkedLeagueSection.tsx` is no longer imported anywhere. Its Refresh/Disconnect logic has moved into `SleeperConnectedState` and `EspnConnectedState`. Delete both the component and its test.

**Files:**
- Delete: `web/src/components/LinkedLeagueSection.tsx`
- Delete: `web/src/tests/components/LinkedLeagueSection.test.tsx`

- [ ] **Step 1: Confirm LinkedLeagueSection is not imported anywhere**

```bash
grep -r "LinkedLeagueSection" /Users/karlkell/Code/AutoTiers/web/src/
```

Expected: zero results (or only the two files we're about to delete). If any other file still imports it, update that import before deleting.

- [ ] **Step 2: Delete the files**

```bash
rm /Users/karlkell/Code/AutoTiers/web/src/components/LinkedLeagueSection.tsx
rm /Users/karlkell/Code/AutoTiers/web/src/tests/components/LinkedLeagueSection.test.tsx
```

- [ ] **Step 3: Run the full frontend test suite**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run 2>&1 | tail -5
```

Expected: `Tests N passed (N)` with no failures. The count will be lower than before (the 6 LinkedLeagueSection tests are gone) but no new failures should appear.

- [ ] **Step 4: Final type-check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C /Users/karlkell/Code/AutoTiers add -u web/src/components/LinkedLeagueSection.tsx web/src/tests/components/LinkedLeagueSection.test.tsx
git -C /Users/karlkell/Code/AutoTiers commit -m "chore: remove LinkedLeagueSection — absorbed into tab panel connected states"
```

---

## Self-Review Corrections (Task 4)

Two spec requirements were missing from the Task 4 implementation above. Apply these patches as part of Task 4 Step 3 before running the tests.

### Fix A: Yahoo connected state

The spec says the Yahoo tab should show a connected-state card when `user.yahoo_subject` is set, with an Unlink button. The Task 4 implementation always shows the Connect button. Add the following to `LinkedAccountsDialog.tsx`:

**1. Add `unlinkYahoo` to the auth import:**
```tsx
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle, unlinkYahoo } from "@/api/auth";
```

**2. Add `yahooBusy` state and `handleYahooDisconnect` alongside the Google equivalents:**
```tsx
const [yahooBusy, setYahooBusy] = useState(false);

async function handleYahooDisconnect() {
  setError(null);
  setYahooBusy(true);
  try {
    await unlinkYahoo();
    await onRefresh();
  } catch (e) {
    setError(e instanceof ApiError ? e.message : "Disconnect failed. Please try again.");
  } finally {
    setYahooBusy(false);
  }
}
```

**3. Replace the `case "yahoo":` panel with:**
```tsx
case "yahoo":
  if (user.yahoo_subject) {
    return (
      <div className="space-y-3">
        <div className="rounded-lg border-2 border-green-500 bg-green-50/50 p-3">
          <div className="mb-1 flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500">
              <span className="text-[10px] font-bold text-white">✓</span>
            </div>
            <span className="text-sm font-bold text-green-700">Connected!</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Yahoo account linked · Fantasy league import coming soon
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={yahooBusy}
          aria-label="Disconnect Yahoo"
          onClick={handleYahooDisconnect}
        >
          Disconnect
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-3 py-2">
      <p className="text-sm text-muted-foreground">
        Connect via Yahoo OAuth. We'll find your Yahoo Fantasy leagues automatically after
        you authorize.
      </p>
      <Button className="w-full" onClick={handleYahooConnect}>
        <YahooIcon /> Continue with Yahoo
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        You'll be redirected to Yahoo, then brought back here.
      </p>
    </div>
  );
```

**Add a test for the Yahoo connected state** (add to `LinkedAccountsDialog.test.tsx`):
```tsx
it("Yahoo tab shows connected state when user.yahoo_subject is set", async () => {
  render(
    <LinkedAccountsDialog open={true} onOpenChange={noop}
      user={{ ...baseUser, yahoo_subject: "y-sub" }}
      onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
  );
  const u = userEvent.setup();
  await u.click(screen.getByRole("button", { name: /^yahoo$/i }));
  expect(await screen.findByText(/connected!/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /disconnect yahoo/i })).toBeInTheDocument();
});
```

Also add `unlinkYahoo: vi.fn()` to the `vi.mock("@/api/auth", ...)` block in the test file.

---

### Fix B: Green dot on connected tab labels

The spec says connected platforms show a green dot on their tab label. In the `TABS.map()` rendering in `LinkedAccountsDialog`, add a `isConnected` check:

```tsx
{TABS.map(({ id, label, Icon, comingSoon }) => {
  // "connected" = has a linked league for this provider, OR Yahoo OAuth is linked
  const isConnected =
    (id === "yahoo" && !!user.yahoo_subject) ||
    (activeProfile?.linked_league?.provider === id);
  return (
    <button
      key={id}
      aria-label={label}
      disabled={comingSoon}
      onClick={() => setActiveTab(id)}
      className={cn(
        "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-2.5 text-xs font-medium transition-colors",
        activeTab === id
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:text-foreground",
        comingSoon && "cursor-not-allowed opacity-40",
      )}
    >
      <Icon />
      {label}
      {isConnected && (
        <span className="ml-0.5 h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
      )}
      {comingSoon && <span className="ml-0.5 text-[10px] font-normal">(soon)</span>}
    </button>
  );
})}
```

No additional tests required for the green dot — it's a purely visual indicator with no interactive behavior.

---

## Post-implementation verification

After all tasks complete, run this full sweep to confirm nothing broke across auth, linked league, and integration paths:

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run 2>&1 | tail -5
```

Expected: all tests pass, no type errors.
