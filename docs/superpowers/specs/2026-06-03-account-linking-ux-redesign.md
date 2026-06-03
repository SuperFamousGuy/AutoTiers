# Account Linking UX Redesign

**Date:** 2026-06-03  
**Status:** Approved  
**Scope:** `web/src/components/LinkedAccountsDialog.tsx`, `EspnConnectForm.tsx`, `SleeperConnectForm.tsx`, `Header.tsx`

---

## Problem

The current account linking experience has three compounding issues:

1. **Flow confusion** — clicking Connect for Sleeper or ESPN replaces the entire dialog body in-place with no breadcrumb, step indicator, or way back. Users don't know where they are.
2. **ESPN private league complexity** — the only path for private leagues requires users to open browser DevTools, navigate to the Application/Storage tab, and manually copy two cookie values. This is a highly technical task that most users have never done, and the instructions have been reported as non-functional.
3. **Mental model mismatch** — Yahoo is both an OAuth identity provider and a fantasy sports platform. The current UI groups it with Google (pure identity) rather than with Sleeper and ESPN (fantasy platforms), which is confusing. Only Google is a pure sign-in provider.

Secondary: the entry point ("Linked Accounts" in the hamburger menu) doesn't communicate the user's actual goal.

---

## Design Decisions

### 1. Rename and reframe the entry point

| Before | After |
|--------|-------|
| "Linked Accounts" (hamburger menu item) | "Connect Your League" |
| `<DialogTitle>Linked Accounts</DialogTitle>` | `<DialogTitle>Connect Your League</DialogTitle>` |

The new name is goal-oriented. Users want to connect a fantasy league so AutoTiers can import their settings — not manage abstract "linked accounts."

### 2. Replace in-place content swap with platform tabs

The dialog body gets a persistent tab strip at the top: **Sleeper · ESPN · Yahoo · NFL Fantasy · CBS Sports**. Clicking a tab switches the panel content without navigation — no back button needed, no context loss.

- NFL Fantasy and CBS remain visible but are disabled with a "Coming soon" placeholder.
- The active tab is highlighted; connected platforms show a small green dot on their tab label.
- The tab strip is the permanent chrome for the dialog — it does not disappear when a sub-form is active.

### 3. Reposition Yahoo as a fantasy platform

Yahoo Fantasy moves from the OAuth identity section into the platform tab strip alongside Sleeper and ESPN. Its connect flow uses Yahoo OAuth (same redirect mechanism as before), but framed as "connect your Yahoo Fantasy league" rather than "link your Yahoo account."

**Scope of this redesign:** the Yahoo tab shows a single "Continue with Yahoo" OAuth button and, after OAuth completes, a connected-state card (league name if one is already linked, otherwise "account linked — no league"). A full post-OAuth league picker (equivalent to Sleeper's username → league-select flow) is **out of scope here** — it requires new backend work and is tracked as a follow-up (see Open Questions).

### 4. Demote Google to a quiet footer

Google is a pure sign-in identity — it has no fantasy league data. It moves out of the main dialog body into a footer row at the bottom of the dialog, clearly labeled "Sign-in only · no fantasy league." A small "Link" / "Unlink" button is present but visually secondary.

### 5. Sleeper: stepped panel with step indicator

The Sleeper tab uses a 2-step flow with an explicit step indicator (Option B from design review):

- **Step 1 — Find your account:** Username field + "Find My Leagues →" button. Step indicator shows `① Find your account ── ② Pick league`.
- **Step 2 — Pick league:** Step 1 checkmarks green; step 2 becomes active. League dropdown shown. "← Wrong username?" link returns to step 1 without losing the username value.

This removes the silent "form contents changed on me" confusion of the previous in-place swap.

### 6. ESPN: public/private toggle gates the credential flow

The ESPN tab opens with a **Public / Private** toggle at the top. Default is Public.

**Public league path:**
- League ID field + inline hint ("Find it in your ESPN league URL: /fantasy/football/leagues/**336041**")
- Connect button

**Private league path:**
- League ID field (same as above)
- A credential section labeled "🍪 Private credentials" with a "How to find these ↗" help link
- SWID and espn_s2 fields inside
- Connect button

**ESPN private credential UX — researcher findings incorporated:**

The SWID/espn_s2 cookie method is confirmed working at the protocol level (verified through August 2025). The previous instruction copy in `EspnConnectForm` likely referenced "ESPN Cookie Finder" — that extension broke on Chrome 138+ (July 2025, Manifest V2 deprecation) and must not be recommended.

The industry standard across all production fantasy tools (FantasyPros, PFF, GameDayBot, Flock Fantasy) is a browser extension — not DevTools and not a bookmarklet. ESPN's auth cookies are HttpOnly and inaccessible to page-level JavaScript, so a bookmarklet approach will not work.

**Recommended UX for the private credential section:**

Replace the current `<details>` DevTools walkthrough with:

1. A short explanation: "ESPN private leagues require two cookie values from your ESPN account. The easiest way to get them is a free browser extension."
2. A primary link to **GameDayBot** (MV3, open-source, copy-paste model — most trustworthy) with a secondary mention of the **PFF extension**.
3. A "Do it manually instead" expandable fallback that retains the existing DevTools instructions for users who can't install extensions — framed as advanced/fallback, not the default path.
4. The SWID and espn_s2 input fields remain unchanged (the cookies themselves are still the mechanism).

**Do not** name "ESPN Cookie Finder" (Hashtag Fantasy) anywhere — it is non-functional on Chrome 138+.

Note: ESPN session cookies are long-lived (months to a full season) but invalidated on password change or ESPN-forced re-auth. The `EspnAuthRequired` error path should surface a clear "your ESPN credentials have expired — reconnect" prompt rather than a generic error (this is a backend concern, out of scope for this UI redesign but noted for a follow-up).

### 7. Success / connected state

After a successful connect, the tab panel transitions to a confirmation view:

- Green bordered card with a ✓ badge, league name, platform, season, and team count
- "Refresh" and "Disconnect" action buttons below the card
- Other platform tabs remain accessible — users can keep connecting without closing the dialog

This replaces the previous silent form-close behaviour.

---

## Component Changes

### `LinkedAccountsDialog.tsx` — significant rewrite

**Remove:**
- `activeForm` state (`"sleeper" | "espn" | null`) and the conditional full-body swap
- The flat `<ul>` listing Google, Yahoo, Sleeper, ESPN as peer rows
- `onConnectSleeper` / `onConnectEspn` prop threading to `LinkedLeagueSection`

**Add:**
- `activeTab` state (`"sleeper" | "espn" | "yahoo" | "nfl" | "cbs"`, default `"sleeper"`)
- Tab strip component (or inline tabs) at the top of `DialogContent`
- Per-tab panel rendering: `<SleeperTab>`, `<EspnTab>`, `<YahooTab>`, `<ComingSoonTab>`
- Google footer row (replaces Google from the main list)
- Pass `onRefresh` and `activeProfile` down to each tab panel

**Props unchanged:** `open`, `onOpenChange`, `user`, `onRefresh`, `initialError`, `activeProfile`

### `SleeperConnectForm.tsx` — moderate update

**New prop:** add `profile: Profile` (the full active profile, not just `profileId`). The connected state is determined from `profile.linked_league?.provider === "sleeper"` inside the component.

- Add step indicator UI (two-node progress bar) above the form
- Step 1: username entry (existing logic unchanged)
- Step 2: league picker (existing `select` logic unchanged) with step 1 shown as green ✓
- Add "← Wrong username?" link on step 2 that calls `setStep("username")` without clearing `username` state
- **Connected state view:** when `profile.linked_league?.provider === "sleeper"`, render the green confirmation card (league name, season, team count) + Refresh/Disconnect instead of the connect form. Refresh/Disconnect logic moves in from `LinkedLeagueSection.tsx`.

### `EspnConnectForm.tsx` — moderate update

**New prop:** add `profile: Profile` (same reasoning as Sleeper above).

- Add `isPrivate` toggle as a **two-button selector at the top** (replacing the checkbox)
- Public path: League ID field only (existing logic)
- Private path: League ID field + credential section (existing SWID/espn_s2 fields, improved layout)
- Instruction content in the private section: placeholder pending researcher findings; keep existing `<details>` content for now, swap it out when research lands
- **Connected state view:** when `profile.linked_league?.provider === "espn"`, render the green confirmation card + Refresh/Disconnect instead of the connect form.
- Remove `onCancel` prop — no longer needed now that tabs handle navigation

### `Header.tsx` — one-line change

```tsx
// Before
<DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
  Linked Accounts
</DropdownMenuItem>

// After
<DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
  Connect Your League
</DropdownMenuItem>
```

### `LinkedLeagueSection.tsx` — absorbed into dialog tabs

This component's Refresh/Disconnect logic moves into the connected-state view inside each tab panel. `LinkedLeagueSection.tsx` can be deleted once the redesign ships, or kept as an internal helper if the tab panels share enough structure to warrant it. Decide at implementation time.

---

## Out of Scope

- ESPN private credential instruction content — depends on researcher findings; ships as a follow-up
- Yahoo Fantasy league picker after OAuth — the OAuth redirect already works; the post-auth league picker is a new backend + frontend feature, tracked separately
- NFL Fantasy and CBS integrations
- Mobile / responsive layout adjustments beyond what the tab strip naturally provides
- Onboarding nudge / first-run guidance (worthy follow-up, not this spec)

---

## Open Questions

1. **ESPN researcher findings** — once the `autotiers-ff-knowledge` skill is updated with ESPN auth research, the private credential UX section of `EspnConnectForm` should be revisited. If a bookmarklet or browser extension approach is viable, the SWID/espn_s2 fields may be replaceable with a one-click flow.

2. **Yahoo post-OAuth league picker** — currently Yahoo OAuth connects the account but doesn't present a league picker (no equivalent to Sleeper's username→league step). The new tab framing exposes this gap. This is a backend + frontend feature that should be scoped separately after this redesign ships.
