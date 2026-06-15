# Onboarding Walkthrough — Design

## Goal
Replace the shallow, passive 3-line onboarding card with an interactive, replayable guided tour that highlights the real Settings → Rules → Generate → Download CSV elements in sequence, so a first-time user understands what tiers and rules do and where to click.

## Approach
Build a lightweight custom tour (no new dependency) driven by a step machine. Each step names a real DOM anchor (existing panel IDs + two new `data-tour` markers), renders a positioned popover with copy that explains the *why*, and advances via Next/Back or when the user performs the step's action. Keep first-run auto-show; keep the existing localStorage "seen" graceful-degradation; surface a Help/replay control (the existing HelpCircle / "Getting Started Guide" menu item) that restarts the tour.

## User-facing impact
- First run (storage empty / blocked): tour auto-starts on a brief delay after mount, beginning with a centered welcome step.
- Steps (5 total):
  1. **Welcome** (centered, no anchor): "Welcome to AutoTiers — let's build your first draft tier list. ~30 seconds." Buttons: Start tour / Skip.
  2. **Settings** (anchor `#panel-settings`): explains scoring format + league size drive the projections. "AutoTiers ranks every player for *your* league's rules — set them here first."
  3. **Rules** (anchor `#panel-rules`): explains rules nudge players up/down. "Weight what you value — e.g. boost rushing QBs. Tiers group players of similar value; rules shape that value."
  4. **Generate** (anchor `[data-tour="generate"]`): "Build your tiers. This crunches projections + your rules into ranked tiers." If the button is disabled, copy notes weights must total 100%.
  5. **Download CSV / Finish** (anchor `[data-tour="download"]` when present, else centered): "Export your tiers to draft day. Done — replay anytime from the help (?) button." Button: Finish.
- Progress indicator: "Step N of 5" + a clickable/visual dot row.
- Controls every step: Back (disabled on step 1), Next/Start/Finish, and an X (Skip tour). Escape skips. The X and Skip persist the "seen" flag exactly as today's dismiss does.
- Replay: HelpCircle button (desktop) and "Getting Started Guide" menu item (mobile) restart the tour from step 1. Replay does NOT clear the seen flag (transient), matching today's `reopen` semantics.
- Highlight: the anchored element gets a visible ring/elevated z-index; the rest of the page dims behind a backdrop. Backdrop click = no-op (does not skip — avoids accidental dismissal), only X/Skip/Escape skip.
- Empty/loading/disabled states: Generate step adapts copy when the button is disabled (no result yet is the norm during the tour). Download step: if no tiers generated yet (`#panel-tiers` has no download button), anchor falls back to the Tiers panel region with copy "After you Generate, download your tiers here."
- Mobile (~375px): popover is full-width docked to the bottom; tour switches the active mobile panel (`setMobilePanel`) to match the step so the highlighted panel is actually visible. Welcome/Finish centered.
- Copy is read-aloud-checked: plain, second person, no marketing filler.

## Code-facing impact
- **New** `web/src/components/OnboardingTour.tsx` — the tour overlay: backdrop, positioned popover, progress, controls, focus trap, keyboard handling. Consumes a `steps` array + current index + callbacks.
- **New** `web/src/lib/onboardingSteps.ts` (or inline const) — the ordered step definitions: id, anchor selector, title, body, optional `mobilePanel` to switch to, whether centered.
- **Rewrite** `web/src/hooks/useOnboarding.ts` — extend to a step machine: `{ active, stepIndex, totalSteps, start, next, back, goTo, skip, finish }`. Preserve `showOnboarding`→`active`, `dismiss`→`skip`/`finish` (both persist seen), `reopen`→`start` (transient). Keep storage graceful-degradation verbatim. Keep first-run seed logic.
- **Replace** `web/src/components/OnboardingCard.tsx` usage in `App.tsx` with `OnboardingTour`. Keep the password-reset-takes-the-slot precedence (tour must not start while `resetToken` is set). OnboardingCard.tsx is deleted (its tests too) — superseded.
- **Edit** `web/src/components/GenerateButton.tsx` — add `data-tour="generate"` to the button.
- **Edit** `web/src/components/TiersPanel.tsx` — add `data-tour="download"` to the Download CSV button.
- **Edit** `web/src/App.tsx` — wire the new hook API; pass `onShowOnboarding={start}` to Header (unchanged prop name acceptable); render `<OnboardingTour>` in the onboarding slot; allow the tour to call `setMobilePanel` per step.
- **New tests** `OnboardingTour.test.tsx`, rewrite `useOnboarding.test.ts` for the step machine. Keep all existing graceful-degradation + seen-flag assertions; add step navigation, focus, escape-skips, finish-persists, replay-is-transient.
- Anchors used: `#panel-settings`, `#panel-rules`, `#panel-tiers` (existing, stable), `[data-tour="generate"]`, `[data-tour="download"]` (new). Selecting by these is resilient to copy changes.

## Math / statistical claims
None. No scoring, clustering, weighting, or distribution change. Mathematician not consulted (deliberate).

## FF heuristic basis
None debatable. Tour copy describes existing app mechanics ("rules shape player value, tiers group similar value"); it makes no new claim about player/positional behaviour. Researcher not consulted (deliberate).

## Out of scope
- Persisting *which* step the user reached (resume mid-tour across reloads) — tour always restarts at step 1.
- Analytics/telemetry on tour completion or drop-off.
- A/B copy variants or localization.
- Re-anchoring the tour live if the user resizes between desktop/mobile mid-step (tour positions on step entry; a mid-step viewport flip is not re-solved).
- Driving a real Generate during the tour (the tour explains the button; it does not auto-click it).

## Open questions
None blocking. Decided inline: backdrop click is a no-op (not a skip) to prevent accidental dismissal; this is the one deviation from "dialog conventions" and is intentional for a tour.
