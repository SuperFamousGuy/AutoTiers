# Mobile Responsive UI — Design

## Goal

Make AutoTiers usable on phones (375px–768px viewport widths) during draft day, without breaking the existing desktop layout.

---

## Approach

The app already has a responsive grid in `App.tsx` (`grid-cols-1 lg:grid-cols-[300px_...]`), and `RulesPanel` has a scrollable tab strip that wraps well. The friction is not the grid itself — it is that below `lg` breakpoint, the three panels stack vertically and together fill far more than one screen height, the header is dense, the dialogs lack safe-area awareness, and several smaller interaction targets fall below accessible tap sizes.

The fix strategy is: (1) convert the stacked-panels layout into a tab-switched single-panel view below `lg`; (2) tighten the header so it survives narrow widths without clipping; (3) add edge padding and `max-h`/`overflow` guards to dialogs for small screens; (4) bring touch targets up to 44px minimum where they currently fall short. No new component libraries. No changes to the desktop (`lg:`) layout.

---

## User-facing impact

### What the user sees on a phone today (friction points, ranked)

**1. Three panels stacked with no navigation — critical**
Below `lg`, `App.tsx` renders `SettingsPanel`, `RulesPanel`, and `TiersPanel` stacked in a single scroll. The main container uses `overflow-hidden` at the `main` level. On mobile this means the user either sees only the top portion of Settings and must scroll a very long page to reach Tiers, or (more likely) the panels are height-constrained and their content is clipped. The Tiers output — the primary deliverable on draft day — is buried at the bottom.

**2. Header overflow — high**
`Header` is `flex items-center justify-between px-6 py-4` with: Logo + DataFreshness on the left; ProfilePicker (dropdown) + Undo button + GenerateButton (large, `size="lg"` = `h-11 px-8`) + HelpCircle + DarkMode toggle + Hamburger on the right. On 375px that right cluster is 8+ items and will either overflow or crush the logo. `DataFreshness` renders a text string ("Data updated 3 days ago") that adds width. There is no `sm:` breakpoint hiding any of these elements.

**3. Dialog clipping on small screens — high**
`DialogContent` uses `fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 ... max-w-md p-6`. On a 375px-wide screen, `max-w-md` is 28rem = 448px, wider than the viewport, so the dialog clips both sides. The `p-6` padding inside also reduces useful dialog width. `LinkedAccountsDialog` is especially affected: it renders a 5-tab strip (`Sleeper / ESPN / Yahoo / NFL / CBS`) at `flex overflow-x-auto` — this scrolls on mobile but the tabs are `px-4` wide, so on 375px only 2–3 tabs are visible without scrolling, with no scroll affordance.

**4. GenerateButton is too prominent for mobile header — medium**
The `Generate` button is `size="lg"` (`h-11 px-8`). On mobile it should either be `size="default"` in the header, or moved to a sticky footer/floating action button. Keeping it `size="lg"` in a header that's already crowded is the main contributor to friction #2.

**5. SettingsPanel touch targets in Bonuses section — medium**
The Bonuses section uses `<Switch>` alongside a `<Label>`. The `Switch` components and their labels have adequate tap area (shadcn Switch is a reasonable size). However, the `flex items-center justify-between` layout means a user could easily tap the space between the label and the switch on a narrow screen and hit nothing. The actual touch target on the switch itself is fine; the label is not wired as a tap target for the switch (it has `htmlFor` but the switch's hit area is small).

**6. RuleItem suggestion buttons ("Low / High") — medium**
`RuleItem`'s expanded panel has `flex items-center justify-between gap-2 flex-wrap` with three elements: a "Low" suggestion button, a numeric input, and a "High" suggestion button. At 375px in the panel column (which at `grid-cols-1` takes full width minus `p-6` = 327px, then `pl-9 pr-2` indented = ~268px), these three elements should fit horizontally but the buttons are `px-2 py-0.5` which produces a touch target well under 44px tall (roughly 20px). This is a touch-target gap, not an overflow gap.

**7. PlayerCard row density — medium**
Each `PlayerCard` row is `py-2.5` (10px top + 10px bottom) with a 44px headshot (`w-11 h-11`). The row is finger-tappable but the chevron expand button (`h-4 w-4` with no padding) at the trailing end has an effective tap area of 16×16px — far below 44px. A user trying to expand a player card on mobile will frequently miss this target.

**8. ManageProfilesDialog — low**
On mobile, each profile row renders `[name] [Rename] [Delete-icon]` in a `flex items-center justify-between gap-2`. When in edit mode it becomes `[Input] [Save] [Cancel]` in the same row. At 375px the input plus two buttons will be very tight. Not a blocker but needs wrapping.

**9. FavoritesDialog / FavoritesPanel — low**
`FavoritesDialog` sets `max-h-[90vh] overflow-y-auto`. The team grid is `grid-cols-4` per division which renders 4 buttons side-by-side. At 375px each button is ~(375 - 2*16px padding - 3*8px gap) / 4 ≈ 77px wide. That's probably fine. However the dialog itself doesn't have horizontal padding safe-areas. The player search result rows (`flex items-center justify-between`) with an Add/Remove button should fit but the button is `size="sm"` and may have marginal touch area.

**10. DataFreshness in header — low**
`DataFreshness` renders an inline `<span>` in the header left cluster. On narrow widths it competes with the Logo for space. It should hide on mobile and be accessible via another path (e.g., the hamburger menu or a tooltip on the Logo).

### What the user sees after the fix

- On a phone: a bottom tab bar (or a top panel-switcher strip) lets the user move between Settings, Rules, and Tiers without scrolling. The active panel fills the screen below the header.
- The header is compact on mobile: Logo left, Generate button (default size) + Hamburger right. DataFreshness hidden on small screens. ProfilePicker moved into the hamburger menu on small screens or collapsed into an icon.
- Dialogs inset from screen edges on mobile (safe padding, `max-h` with overflow scroll).
- LinkedAccountsDialog tab strip remains horizontally scrollable but gets a visual indicator it is scrollable.
- PlayerCard chevron target enlarged.
- RuleItem suggestion buttons enlarged vertically.

### States affected

| Component | Mobile state change |
|---|---|
| App main layout | `< lg`: tab-switched single-panel; `>= lg`: existing 3-column grid unchanged |
| Header | `< lg`: compact — Logo + Generate (default size) + Hamburger; `>= lg`: existing layout unchanged |
| SettingsPanel | Rendered inside active tab; scrolls internally; no layout change |
| RulesPanel | Rendered inside active tab; scrolls internally; no layout change |
| TiersPanel | Rendered inside active tab; scrolls internally; no layout change |
| DialogContent (ui primitive) | Add `mx-4` safe inset + `max-h-[calc(100dvh-2rem)] overflow-y-auto` for all screens below `sm` |
| PlayerCard chevron | Wrapped in a `p-2 -m-2` hit-area expander |
| RuleItem suggestion buttons | `py-2` minimum (from current `py-0.5`) to reach ~32px height |

### Loading/error/empty states — not affected by this change
The loading skeletons in `TiersPanel` and `RulesPanel` already use full-width `rounded-md` blocks that respond to container width. No changes needed there.

---

## Code-facing impact

### Files the Engineer must touch

**`web/src/App.tsx`**
- The `<main>` element currently: `flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden`
- Change: below `lg`, replace the stacked-column layout with a tabbed single-panel. Add a `MobilePanel` state variable (`"settings" | "rules" | "tiers"`, default `"tiers"` — draft day users want to see tiers first). Add a `MobilePanelTabBar` component (or inline it in App) that renders 3 tab buttons below the header, visible only `< lg`. Each panel renders only when its tab is active (`< lg`) OR always (`>= lg`). The `lg` three-column layout is left completely unchanged.
- The `profilePicker` prop passed to `Header` should be hidden on mobile (`hidden lg:flex`), with the profile picker accessible via the hamburger menu instead.

**`web/src/components/Header.tsx`**
- Current: `flex items-center justify-between border-b bg-card px-6 py-4`. No breakpoint variants.
- Changes needed:
  - `px-6` → `px-4 lg:px-6` (reduce padding on mobile)
  - `DataFreshness` component: wrap in `hidden lg:inline` so it disappears on mobile
  - `GenerateButton`: pass a new `compact` prop (or use a `className` override) to render `size="default"` below `lg` and `size="lg"` at `lg:`. Alternatively, just always use `size="default"` — the large size is not critical.
  - `profilePicker` slot: on mobile, the profile picker is hidden from the header (handled by the `hidden lg:flex` wrapper in App.tsx). The hamburger menu should expose the current profile name and a link to manage profiles.
  - `HamburgerMenu`: Add "Current profile: [name]" as a disabled menu item when a profile is active. Already shows "Connect Your League" — that is correct.
  - `py-4` → `py-3 lg:py-4` to reduce header height on mobile.

**`web/src/components/ui/dialog.tsx`**
- `DialogContent` base class currently: `fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-md border bg-card p-6 shadow-lg`
- Change: add `mx-4 sm:mx-auto` so the dialog has a 16px inset from screen edges on very small screens. The `max-w-md` clamp still applies at larger sizes. Add `max-h-[calc(100dvh-2rem)] overflow-y-auto` to prevent dialogs taller than the viewport from clipping off-screen.
- This affects ALL dialogs (AuthDialog, LinkedAccountsDialog, ManageProfilesDialog, FavoritesDialog). Verify each one after the change.

**`web/src/components/LinkedAccountsDialog.tsx`**
- Tab strip: `flex overflow-x-auto border-b border-border`. The `overflow-x-auto` is already correct. Add a `scrollbar-thin` or a visual fade/mask on the right edge to hint at scroll. Since we can't add a new CSS class for the mask without `index.css` changes, use a `relative` wrapper + an `after:` pseudo-element gradient. This is a CSS-only change.
- Tab buttons: `px-4 py-2.5` — adequate tap height (10+10+text ≈ 34px). Consider `py-3` to push them to 44px.
- Google footer: `flex items-center justify-between border-t border-border px-6 py-3` — on mobile `px-6` is generous for a 375px dialog that already has `mx-4`. Change to `px-4`.

**`web/src/components/PlayerCard.tsx`**
- The expand chevron `<ChevronDown>` is inside the full-width button (`flex w-full items-center gap-3 px-3 py-2.5`). The button itself is the tap target and it is full-row — this is actually fine. The `py-2.5` means the row is `10+10+44px (headshot)` = at least 64px tall. The chevron is not a separate tap target; the whole row is the toggle. No change needed for the expand.
- However, the rule adjustment in `RuleItem` does have separate small buttons (see below).

**`web/src/components/RuleItem.tsx`**
- `CollapsibleTrigger` has class `p-1 -m-1` — 8px padding total, so 16+8+8 = 32px effective. Borderline. Change to `p-2 -m-2` for 40px effective target.
- Suggestion buttons (`Low` / `High`): currently `px-2 py-0.5` — ~20px tall. Change to `px-2 py-2` — ~36px tall. This affects the expanded detail panel layout slightly; the `flex-wrap` ensures they reflow if needed.

**`web/src/components/ManageProfilesDialog.tsx`**
- Profile row in view mode: `flex items-center justify-between gap-2`. On narrow widths the `[Rename] [Delete-icon]` pair could overlap the name. Add `flex-wrap` and ensure the name span truncates: it already has `flex-1 truncate`.
- Profile row in edit mode: `[Input] [Save] [Cancel]` — this is likely fine given the dialog is now `mx-4` narrower, but add `flex-wrap` as a safety measure.

### New component: `MobilePanelTabBar` (inline in App.tsx or extracted to `web/src/components/MobilePanelTabBar.tsx`)

A three-button tab bar visible only below `lg`. Renders between the Header/OnboardingCard and the main panels. Buttons: "Settings", "Rules", "Tiers". Active tab gets `bg-primary text-primary-foreground`; inactive gets `bg-muted text-muted-foreground`. Keyboard: `role="tablist"`, each button `role="tab"` with `aria-selected`. The corresponding panels use `role="tabpanel"`.

```
Props:
  active: "settings" | "rules" | "tiers"
  onChange: (tab: "settings" | "rules" | "tiers") => void

Layout: flex w-full border-b bg-card (visible lg:hidden)
Each tab: flex-1 py-3 text-sm font-medium text-center
```

This is the only genuinely new component this PR introduces.

### `web/src/index.css`
No changes. The viewport meta tag is already correct (`<meta name="viewport" content="width=device-width, initial-scale=1.0">` is in `index.html`). No new CSS classes.

### Files NOT changed

- `RulesPanel.tsx` — internal tab strip already works on mobile; the panel itself will render in its own tab slot
- `SettingsPanel.tsx` — no layout changes; renders fine in a full-width column on mobile
- `TiersPanel.tsx` — no layout changes; renders fine in a full-width column on mobile
- `SleeperConnectForm.tsx`, `EspnConnectForm.tsx`, `YahooConnectForm.tsx` — already `w-full` inputs; no changes needed
- `FavoritesPanel.tsx` — team grid `grid-cols-4` will be ~77px per cell on 375px, acceptable
- `AuthDialog.tsx` — inherits dialog fix; no further changes needed
- `ScoreWeights.tsx` — slider is `w-full`; no changes needed
- `PositionFilter.tsx` — already `flex flex-wrap gap-1`; works on mobile

---

## Math / statistical claims

N/A. This design involves no scoring formula, weight, ranking algorithm, or statistical claim.

---

## FF heuristic basis

N/A. This design involves no fantasy football domain judgment. The default mobile tab is "Tiers" (the output panel) rather than "Settings" on the grounds that users on draft day have already configured their settings and need to see the tier list. This is a UX judgment, not an FF heuristic.

---

## Out of scope

The following items were identified but are deliberately excluded from this PR to keep scope shippable.

1. **Offline/PWA support** — a draft-day phone user losing connection mid-draft would benefit from a service worker cache. Separate issue.
2. **Touch-swipe between panels** — after the tab-switch is in place, swipe gestures to navigate panels would improve mobile feel. Deferred; requires either a library (`react-swipeable`) or custom pointer-event handling — scope risk.
3. **Landscape phone orientation** — at 667px wide (iPhone landscape) the `lg:` breakpoint at 1024px still shows mobile layout; a user in landscape gets the tab-switched layout, not the 3-column layout. A `md:` breakpoint variant (e.g., `md:grid-cols-[260px_minmax(0,1fr)]` for Settings+Tiers side-by-side) would help. Deferred.
4. **DataFreshness accessibility on mobile** — hiding DataFreshness on mobile means the user cannot see data age on a phone. A follow-up could surface this in the hamburger menu or as a toast on generate. Deferred.
5. **ProfilePicker in hamburger menu** — this design moves the ProfilePicker off the header on mobile but the hamburger menu's dropdown (`DropdownMenu`) is not a full-fledged profile switcher. A follow-up could add a proper profile-switching sheet or bottom drawer on mobile.
6. **Bottom navigation drawer for Generate** — moving Generate to a sticky bottom bar on mobile (a common pattern) would free header space entirely. Deferred; requires layout restructuring beyond what's in scope.
7. **Pinch-to-zoom player cards** — no change; the existing viewport meta tag already allows zoom.
8. **`safe-area-inset-*` CSS for iPhone notch/home indicator** — dialogs and fixed elements near screen edges should use `env(safe-area-inset-*)` padding on iOS. Deferred; low impact except for notch devices.

---

## Open questions

1. **Default mobile tab: "Tiers" vs "Settings"?** This design defaults to "Tiers" on mobile. The argument is that on draft day the user has already configured settings. But a first-time user needs Settings first. Should the default be "Tiers" always, or should it be "Settings" on first visit (no prior generate result) and "Tiers" after a result is present? Manager/product decision.

2. **ProfilePicker on mobile: hamburger-only vs chip in a panel?** The design hides the ProfilePicker from the header on mobile and adds a "Current profile: [name]" disabled item in the hamburger. Is that sufficient, or should there be an in-panel way to switch profiles without opening the hamburger? If the user is on the Settings tab, they could reasonably expect a profile-switch affordance there.

3. **GenerateButton placement on mobile: header vs sticky footer?** The design keeps Generate in the header on mobile (just smaller). The sticky footer alternative (#6 in out-of-scope) is better UX but bigger scope. Confirm the header placement is acceptable for this PR.

4. **Tab label copy: "Settings" / "Rules" / "Tiers" or shorter?** At 375px with three equal tabs, each label gets about 115px. "Settings", "Rules", "Tiers" all fit. No issue, but confirming this is the desired nomenclature (vs e.g. "Config" or abbreviated forms).

5. **`LinkedAccountsDialog` scroll indicator:** The right-edge fade/mask approach for the tab strip requires a CSS `after:` pseudo-element gradient on the wrapper. This is a minor `index.css` addition. Alternatively, skip the visual affordance — the `overflow-x-auto` behavior is the same either way. Confirm whether the scroll indicator is required or optional.
