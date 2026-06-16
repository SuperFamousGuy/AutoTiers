# Provide Feedback — Design

_Stage 1 Design Artifact for GitHub issue #88. Transport (SES → fixed inbox) and
entry point (Header hamburger menu → dialog) are settled by the user; this artifact
specifies the contract the Engineer implements._

## Goal
Let any AutoTiers user send free-text feedback from inside the app, delivered as an
email to a fixed, configurable team inbox.

## Approach
Add a "Provide Feedback" item to the Header hamburger menu that opens a small
`FeedbackDialog` (mirroring the existing dialog pattern). The dialog POSTs the message
to a new `POST /api/feedback` endpoint, which formats an email and sends it via the
existing `EmailSender` to a config-driven recipient address. No new persistence, no new
auth, no new infra — it reuses the SES email layer already shipped for auth emails.

## User-facing impact

### Entry point
- New menu item **"Provide Feedback"** in `HamburgerMenu` (`Header.tsx`).
- **Visibility: shown to BOTH logged-in and logged-out users.** Justification: feedback
  is not an account action — a logged-out visitor who hits friction is exactly who you
  most want to hear from, and the SES transport does not depend on the user being
  authenticated (we send to a fixed inbox, not to the user). Placement:
  - Logged-in branch: after "Favorites", before "Log Out".
  - Logged-out branch: after "Log In / Sign Up".
  - Rendered as `<DropdownMenuItem onSelect={() => setFeedbackOpen(true)}>Provide Feedback</DropdownMenuItem>`.

### The dialog (`FeedbackDialog`)
Mirrors `LinkedAccountsDialog` structure: `Dialog` / `DialogContent` / `DialogTitle`
from `@/components/ui/dialog`, `Button` from `@/components/ui/button`, local `useState`
for `message`, `busy`, `error`. Success is reported via the global `toast()` (the
established success pattern — see `App.tsx` email-verified toast), then the dialog closes.

Contents:
- `DialogTitle`: **"Send Feedback"**
- One short description line: **"Found a bug or have an idea? Tell us — it goes straight to the AutoTiers team."**
- A labelled multiline **message** field (`<label>` + styled `<textarea>`), placeholder
  "What's on your mind?", `rows={5}`, `maxLength={4000}`.
- If the user is logged in and has an email: a muted line **"We'll include your email
  (you@example.com) so we can reply."** (honest disclosure — see Privacy below). If
  logged out or no email: **"Sign in if you'd like a reply — otherwise this is anonymous."**
- Footer: **Cancel** (ghost) + **Send Feedback** (primary).

### Render states (each has a next action)
| State | What the user sees | Next action |
|---|---|---|
| Idle / empty | Textarea empty, "Send Feedback" **disabled** | Type a message |
| Has text | "Send Feedback" enabled | Click Send (or Cmd/Ctrl+Enter) |
| Submitting | "Send Feedback" shows busy + disabled, textarea disabled, Cancel disabled | Wait |
| Success | Dialog closes; toast "Thanks for the feedback!" (variant success) | — (done) |
| Validation error (empty/whitespace-only) | Submit stays disabled; no network call | Type non-whitespace |
| Network/server error | In-dialog `<p className="text-xs text-red-600" role="alert">` with the message; textarea + buttons re-enabled; text preserved | Retry or Cancel |
| Rate-limited (429) | Same red error line: "You're sending feedback too quickly — please wait a moment and try again." | Wait, retry |

Empty-state handling: submit is **disabled until `message.trim()` is non-empty**. The
message is trimmed before sending. No "empty" error toast is ever needed because the
control is disabled.

### Accessibility
- Textarea has an associated `<label htmlFor>` / `id` ("Your feedback"); not a placeholder-only field.
- On dialog open, focus moves to the textarea (Radix Dialog auto-focuses the first
  focusable element; ensure the textarea is first, or set `autoFocus`).
- Keyboard submit: **Cmd/Ctrl+Enter** in the textarea triggers Send (when enabled).
- Error region is `role="alert"` (assertive) so screen readers announce failures.
- `Escape` closes the dialog (Radix default); Cancel button is keyboard reachable.
- Buttons have visible text labels (no icon-only controls), so no `aria-label` needed.

## Code-facing impact

### New backend files
- `backend/app/api/feedback.py` — new router. `POST /feedback`.
- `backend/app/email/templates.py` — add `feedback_email(message: str, sender_email: str | None) -> tuple[str, str]`.
- `backend/app/config.py` — add `feedback_recipient: str` setting.
- `backend/app/main.py` — `app.include_router(feedback.router, prefix="/api")`.
- `backend/tests/test_feedback_api.py` — new test file.

### API contract
`POST /api/feedback`

Request body (Pydantic model `FeedbackRequest`):
```
{ "message": str }   # required; min_length after strip = 1; max_length = 4000
```
- No category field in v1 (kept tight; category is an out-of-scope follow-up).
- The submitting user's email is NOT taken from the request body (untrusted). The
  endpoint reads the authenticated user from the existing auth dependency **if present,
  optionally** — i.e. the endpoint works for anonymous users too. Use an optional-user
  dependency (the same mechanism `/me`-adjacent routes use; if no optional-user
  dependency exists, the Engineer adds a thin one that returns `User | None` without
  raising on missing auth — see Open questions). The email is attached server-side for
  reply context, never accepted from the client.

Response: **HTTP 202**, body `{"detail": "Thanks for the feedback!"}`.
- Rationale for 202 + **synchronous send (awaited, NOT BackgroundTasks)**: unlike
  password-reset (where we deliberately never reveal whether an email exists, so a
  fire-and-forget background send is correct), feedback has no enumeration concern and
  the user benefits from knowing their message actually went through. Await the send so
  a transport failure surfaces as a 5xx the dialog can show ("Couldn't send right now —
  please try again."). Wrap the send so an SES error becomes a clean 502/500 with a
  user-safe detail, not a stack-trace leak.
- Validation failure (empty/oversize) → 422 (FastAPI/Pydantic default). The frontend
  prevents empty via disabled submit; 422 is a backstop.

Rate limiting: reuse the in-process rate-limiter pattern already used by
`forgot_password` (`reset_rate_limiter.check_and_record`). Key by client IP (and by
user id when authenticated). Limit: a small burst (e.g. 5 / 10 min). Over limit → 429.

### Email format (what the team inbox receives)
- **To:** `settings.feedback_recipient`
- **From:** `settings.ses_from_address` (already verified sender).
- **Subject:** `"AutoTiers feedback from <email-or-anonymous>"`
- **Body (text + html):**
  - Line: "From: {sender_email or 'anonymous (not logged in / no email)'}"
  - Line: "Submitted: {UTC timestamp}"
  - Blank line, then the verbatim message.
  - HTML escapes the message (no HTML injection into the team's inbox).

### New config setting
```python
# backend/app/config.py — Settings
# Recipient inbox for in-app "Provide Feedback" submissions. Must be a verified SES
# recipient while SES is in sandbox. Override via FEEDBACK_RECIPIENT env.
feedback_recipient: str = "feedback@autotiers.example"
```
Default uses the `.example` TLD to match `ses_from_address`'s placeholder convention —
prod sets the real address via env. NOT hardcoded in the endpoint.

### New frontend files / edits
- `web/src/api/feedback.ts` — `sendFeedback(message: string): Promise<void>`. The
  response is JSON (`{detail}`), so use `apiFetch<{detail:string}>(...)` — do NOT use the
  raw-fetch empty-body path (that's only for 204). 202-with-JSON-body parses fine.
- `web/src/components/FeedbackDialog.tsx` — new component (props `{ open, onOpenChange }`).
- `web/src/components/ui/textarea.tsx` — **new shadcn-style primitive** (there is no
  textarea primitive today). Mirror `input.tsx` exactly: `React.forwardRef`,
  `React.ComponentProps<"textarea">`, same `cn(...)` class string adapted for multiline
  (drop `h-9`/`file:*`, add `min-h-[80px]`, keep border/ring/focus-visible/disabled
  classes). Adding the primitive (vs inlining) keeps the textarea reusable and matches
  the codebase's "primitives in ui/" convention.
- `web/src/components/Header.tsx` — add the menu item(s) + local `feedbackOpen` state +
  render `<FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />`.
  **Open-state lives LOCAL to `HamburgerMenu`** (like `favoritesOpen`/`authOpen`), NOT
  lifted to `App`. Rationale: `LinkedAccountsDialog` is lifted only because App owns the
  linking-error state and cross-component triggers; feedback has no such cross-cutting
  state, so co-locating it with the menu keeps `App.tsx` and the `Header`/`App` prop
  surface unchanged. No new props on `Header`/`App`.
- Tests: `web/src/tests/components/FeedbackDialog.test.tsx` (render states, disabled
  submit, success-closes, error-shows). Optionally extend a Header test for the menu item.

### Success notification
On success, call `toast({ title: "Thanks for the feedback!", variant: "success" })`
(import `useToast` as `App.tsx` does) and `onOpenChange(false)`. This matches the
established success-feedback pattern and avoids a redundant in-dialog success state.

## Math / statistical claims
N/A — no math in this feature.

## FF heuristic basis
N/A — no fantasy-football domain logic in this feature.

## Privacy
We attach the authenticated user's email server-side (never from the client) so the team
can reply. This MUST be disclosed in the dialog copy ("We'll include your email … so we
can reply."). Logged-out submissions are anonymous and the copy says so. We do not
capture IP in the email body; IP is used only transiently for rate-limiting, consistent
with the existing reset-rate-limiter. No new PII storage (nothing is persisted to the DB).

## Out of scope (each bullet → a GitHub issue if it defers real user value)
1. **Feedback categories / type selector** (bug vs idea vs other). v1 is free-text only.
   → file issue.
2. **Persisting feedback to the database / an admin view.** v1 is email-only; there is no
   in-app record. → file issue.
3. **Attachments / screenshots.** Not in v1. → file issue.
4. **Reply-To set to the submitter's email** so the team can hit "reply" directly. v1
   puts the email in the body only (the SES `send` wrapper takes no Reply-To today;
   adding one is a small SesSender change). → file issue.
5. **Exiting SES sandbox** so feedback from arbitrary senders' addresses isn't required —
   N/A here because recipient is the fixed verified inbox; tracked separately
   (sandbox-exit PENDING per project memory). Not filed as new.

## Open questions (Manager triages before Engineer starts)
1. **Optional-auth dependency:** Does an existing dependency return `User | None` without
   401-ing on anonymous requests? If yes, reuse it. If no, the Engineer adds a thin
   `get_optional_user` that returns `None` when no/invalid cookie is present (must NOT
   raise). This is the only backend mechanism the design assumes but cannot confirm from
   the files the Manager surfaced. NOT a product blocker — the Engineer can build it — but
   the Manager should confirm the auth dependency shape so the Engineer mirrors it
   correctly rather than inventing a parallel one.
