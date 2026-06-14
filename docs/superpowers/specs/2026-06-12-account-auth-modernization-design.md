# Account Auth Modernization — Design

**Date:** 2026-06-12
**Status:** Draft
**Issue:** #87 — Missing Forgot Password
**Branch:** feat/account-auth-87
**Scope:** Backend (auth endpoints, new models, email infra) + Frontend (AuthDialog, LinkedAccountsDialog, new password-management UI)

---

## Goal

Give users a complete, modern password-management experience: forgot-password reset via email, change password while logged in, set a password on OAuth-only accounts, a polished signup form, and soft email verification — all without breaking existing OAuth flows or the "cannot unlink last sign-in method" invariant.

---

## Approach

The work is organized as six independently-shippable slices (see Implementation Slices). The core enabler is a new `auth_tokens` table that stores both password-reset tokens and email-verification tokens, hashed at rest, with TTL and single-use enforcement. An `EmailSender` abstraction with an AWS SES implementation provides all outbound email; tests inject a no-op fake. Frontend changes are concentrated in `AuthDialog.tsx` (signup polish + forgot-password trigger) and a new `PasswordManagementSection` inside `LinkedAccountsDialog.tsx` (change/set-password panel). No client-side routing library exists — the password-reset confirmation page is rendered as a conditional panel within the existing single-page `App.tsx`, gated on a `?token=` query parameter.

---

## User-facing impact

### Flow A — Forgot password (unauthenticated)

**Entry point:** "Forgot password?" link below the password field on the Login tab of `AuthDialog`.

**Step 1 — Request reset**

User sees a single-field form inside the same `AuthDialog` (the dialog swaps its interior content; the outer dialog stays open). Copy:

- Heading: "Reset your password"
- Body: "Enter the email address on your account. If it matches, you'll receive a reset link within a few minutes."
- Field label: "Email address"
- Submit button: "Send reset link"
- Back link: "Back to log in"

Loading state: button becomes "Sending..." and is disabled.

Success state (always shown — whether or not the email exists): "Check your inbox. If that email matches an account, a reset link is on its way. Check your spam folder if you don't see it within a few minutes."

A "Back to log in" link returns to the Login tab. The dialog does not close automatically.

Error state (only for hard failures — rate limit, server error): "Too many requests. Please wait a few minutes before trying again." / "Something went wrong. Please try again."

**Step 2 — Click email link**

The email contains a link in the form `{frontend_url}?reset_token=<urlsafe_base64_token>`. The app reads the query param on load and renders a full-page-width inline panel (not a dialog) above the main content, replacing the onboarding card if visible.

Panel copy:
- Heading: "Set a new password"
- Field: "New password" (with show/hide toggle, strength hint)
- Field: "Confirm new password"
- Submit button: "Save new password"

Loading state: button becomes "Saving..." and is disabled.

Success state: "Your password has been updated. You are now logged in." The panel disappears. If the backend issues a session cookie on successful reset, `AuthContext.refresh()` is called so the user appears logged in.

Error states:
- Token expired (>1 hour): "This reset link has expired. Request a new one." with a "Request new link" button that opens `AuthDialog` on the forgot-password sub-view.
- Token already used: "This reset link has already been used. Request a new one." (same action).
- Token not found / malformed: "This reset link is invalid. Request a new one."
- Password too short (validated client-side before submit, but also a backend guard): "Password must be at least 10 characters."
- Passwords don't match (client-side only): "Passwords do not match."

**OAuth-only account requests reset:**

If the email exists but the account has `password_hash IS NULL` (OAuth-only), the backend still sends the same "check your inbox" response (non-enumeration). However, if the token is used, the reset endpoint sets a new password instead of replacing an existing one — functionally identical to "set password" (Slice C). This is correct behavior; no special case needed in the frontend.

**Unverified email requests reset:**

No restriction. A user who signed up and has not verified their email can still request a password reset. Blocking unverified users from reset would lock them out permanently if they never verified. The reset email itself serves as implicit verification (the token proves the user controls the inbox).

---

### Flow B — Change password (authenticated, has existing password)

**Entry point:** New "Password" section inside `LinkedAccountsDialog`, shown only when `user.has_password === true` (new field on `UserOut`).

Section heading: "Password"

Collapsed state: "Password set. Last changed: never / {relative date}." with a "Change password" button.

Expanded state (form):
- Field: "Current password" (type=password, show/hide toggle)
- Field: "New password" (type=password, show/hide toggle, strength hint)
- Field: "Confirm new password" (type=password)
- Buttons: "Save" (primary), "Cancel" (ghost)

Loading state: "Save" becomes "Saving..." and is disabled.

Success state: form collapses, banner "Password updated." fades out after 3 seconds.

Error states:
- Current password wrong: "Current password is incorrect."
- New password same as current: "New password must be different from current password." (backend check)
- New password too short: "Password must be at least 10 characters."
- Passwords don't match: "Passwords do not match." (client-side)

---

### Flow C — Set password (authenticated, OAuth-only account, no existing password)

**Entry point:** Same "Password" section, shown when `user.has_password === false` AND `user.email !== null`.

If `user.email === null` (e.g., a Yahoo-only account that OAuth'd without a verified email), this section is hidden entirely. Setting a password requires an email — without one, the section cannot appear because there is no credential pair to log in with.

Empty state copy: "No password set. Add one to log in with email." with a "Set password" button.

Expanded state (form):
- Field: "New password" (type=password, show/hide toggle, strength hint)
- Field: "Confirm new password" (type=password)
- Note: "You'll be able to log in with {user.email} and this password."
- Buttons: "Set password" (primary), "Cancel" (ghost)

Success: form collapses, banner "Password set. You can now log in with your email." fades out after 3 seconds.

Error states: identical to Change password except no "current password" field.

---

### Flow D — Signup UX polish

Current `AuthDialog` signup tab has: email, password (min 10 chars), submit. Additions:

1. **Confirm-password field**: "Confirm password". Client-side check: must match `password` before submit is enabled. Error message shown inline: "Passwords do not match."

2. **Show/hide toggle**: Both password fields get an eye-icon button (aria-label: "Show password" / "Hide password"). `type` toggles between `"password"` and `"text"`.

3. **Password-strength hint**: A single line below the password field, computed client-side. Not a red/green traffic light — just a text hint that tracks the most impactful missing requirement:
   - Fewer than 10 chars: "Must be at least 10 characters" (shown in muted red — `text-destructive`)
   - 10+ chars, all lower: "Add uppercase letters, numbers, or symbols" (shown in muted amber — `text-yellow-600 dark:text-yellow-400`)
   - Meets a moderate bar (10+ chars, at least one non-lower): nothing shown (silent pass)

   The strength hint shows only while the field has been interacted with (onBlur or onChange after first keystroke). It does not fire on a pristine untouched field.

4. **"Forgot password?" link on Login tab**: Small text link below the password field. Copy: "Forgot password?" Clicking it replaces the Login form with the forgot-password sub-view (described in Flow A). It does not close the dialog.

5. **Tab-switching clears errors**: Already implemented (`onValueChange={() => setError(null)}`). Preserve this.

6. **"Forgot password?" link placement**: positioned right-aligned as a small secondary link at the same horizontal level as the "Password" label, per modern convention. Example layout:

   ```
   Password                              Forgot password?
   [                                   ]
   ```

---

### Flow E — Email verification

**Philosophy:** soft verification. Signing up grants full access immediately. Email verification is an optional trust-building step surfaced non-intrusively. We do not gate any feature on verification at this time.

**On signup:** after account creation, a verification email is sent asynchronously (best-effort). Failure to send does not fail the signup response. The user is logged in and lands on the app.

**Unverified-state UX:** a dismissible yellow banner in the app header area (below the header bar, above the main content, same slot as onboarding card). It appears on page load when `user.email_verified === false` AND the banner has not been dismissed in this session (session-storage key `"email_verified_banner_dismissed"`).

Banner copy: "Please verify your email. We sent a link to {user.email}. [Resend] [Dismiss]"

- "Resend" fires `POST /api/auth/email/resend-verification`. Success: "Verification email sent." (replaces banner content for 3 seconds, then banner dismisses). Rate-limited: "Please wait a minute before requesting another verification email."
- "Dismiss" hides the banner for the session only (sessionStorage). On next page load it reappears.
- If `user.email_verified === true`, banner never appears.

**Verification link in email:** `{frontend_url}?verify_token=<token>`. On app load, if `verify_token` is present in the query string, the app calls `GET /api/auth/email/verify?token=<token>`, removes the param from the URL, and:
- Success: shows a toast "Email verified. Thank you!" and calls `AuthContext.refresh()` to update `email_verified` in the user object.
- Failure (expired, already used, invalid): shows a toast "This verification link is invalid or has expired. You can request a new one from the banner below." and triggers the unverified banner if not already shown.

**UserOut exposure:** add `email_verified: boolean` field (defaults `false` for existing accounts — migration sets all existing rows to `false`, or `true` for OAuth-sourced emails where `yahoo_email_verified` / `google_email_verified` was true at link time — see Data Model section).

---

### Toast / feedback pattern

All transient success/error messages that appear outside a form use the existing shadcn `toast` primitive (or a minimal inline notification if toast is not yet wired). No new notification library. Messages auto-dismiss after 4 seconds. They carry `role="status"` (success) or `role="alert"` (error) for screen readers.

---

## Code-facing impact

### New: `backend/app/email/`

```
backend/app/email/
  __init__.py
  sender.py          # EmailSender abstract base class (Protocol)
  ses_sender.py      # AWS SES implementation
  templates.py       # HTML + plain-text template builders for each email type
  fake_sender.py     # In-test no-op / capture implementation
```

**`sender.py` — interface:**

```python
from typing import Protocol

class EmailSender(Protocol):
    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> None: ...
```

No base class inheritance. Protocol-based duck typing. Tests inject `FakeSender` which collects sent emails into a list for assertion.

**`ses_sender.py` — implementation:**

Uses `aiobotocore` (already a dependency class in the AWS ecosystem; if not present, add it) to call `ses:SendEmail` via the AWS API. Configuration pulled from `settings`:

```
SES_FROM_ADDRESS    # e.g. "AutoTiers <noreply@autotiers.com>"
SES_REGION          # e.g. "us-east-1"
```

AWS credentials come from the ECS task role (IAM). No credentials in env vars. The task role needs `ses:SendEmail` on `arn:aws:ses:<region>:<account>:identity/<verified-sender>`.

**`templates.py`:**

- `reset_password_email(reset_url: str) -> tuple[str, str]` — returns `(html, text)`
- `verify_email_email(verify_url: str) -> tuple[str, str]` — returns `(html, text)`

Kept minimal: plain branded text emails, single call-to-action button/link. No HTML template engine dependency — f-strings suffice at this scale.

**Injection pattern:**

`EmailSender` instance is created at app startup in `backend/app/main.py` (or the app factory) and stored as an app-level dependency via FastAPI's `app.state`. A FastAPI `Depends` helper `get_email_sender() -> EmailSender` yields `request.app.state.email_sender`. In tests, the fixture overrides `app.state.email_sender` with a `FakeSender` instance before the test client is created.

**Ops checklist (SES setup):**

1. Verify the sender identity/domain in AWS SES (production: domain verification preferred over per-address; sandbox mode requires recipient verification too).
2. Request SES production access (exit sandbox) — file a support case if not already done.
3. Add IAM policy `ses:SendEmail` to the ECS task role, scoped to the verified identity ARN.
4. Set `SES_FROM_ADDRESS` and `SES_REGION` env vars on the ECS task definition (via Terraform).
5. For local dev: set `EMAIL_SENDER_BACKEND=fake` (or leave unset — default to fake in debug mode) so no real emails are sent during development.

---

### New: `backend/app/models/auth_token.py`

```python
class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id:           UUID PK, default uuid4
    user_id:      UUID FK → users.id ON DELETE CASCADE, non-null, indexed
    token_hash:   str, non-null, unique         # SHA-256 hex of the raw token
    token_type:   str, non-null                 # "password_reset" | "email_verify"
    expires_at:   datetime(tz=True), non-null
    used_at:      datetime(tz=True), nullable   # set when consumed; NULL = unused
    created_at:   datetime(tz=True), non-null, default now()
```

**Security properties:**

- Raw token: `secrets.token_urlsafe(32)` (256 bits of entropy — brute-force infeasible).
- Stored token: `hashlib.sha256(raw_token.encode()).hexdigest()`. The raw token is never persisted.
- Single-use: on consume, set `used_at = now()`. Any subsequent use with the same token finds `used_at IS NOT NULL` and returns 400.
- TTL:
  - Password reset tokens: 1 hour (`expires_at = now() + timedelta(hours=1)`)
  - Email verification tokens: 72 hours (`expires_at = now() + timedelta(hours=72)`)
- One-active-per-user-per-type policy: on issuing a new token of a given type for a user, hard-delete any existing unused tokens of the same type for that user first. This prevents token accumulation and ensures the latest link is always the valid one. (Do NOT soft-delete — DELETE FROM auth_tokens WHERE user_id = ? AND token_type = ? AND used_at IS NULL.)
- Expired-but-unused tokens: a background cleanup job is not required at this scale. The "one active per user" delete-on-issue policy prevents accumulation.

---

### Modified: `backend/app/models/user.py`

Add two columns:

```python
email_verified:       Mapped[bool]  = mapped_column(Boolean, nullable=False, default=False, server_default="false")
password_changed_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

`password_changed_at` is set whenever `password_hash` is updated (change password, set password, reset password). Used in the "Change password" UI to display "Last changed: {relative date}".

---

### Modified: `backend/app/schemas/auth.py`

**`UserOut`:** add:
```python
has_password: bool        # user.password_hash is not None
email_verified: bool      # user.email_verified
password_changed_at: Optional[datetime]
```

The `model_validator` that already converts ORM attributes to a dict must be extended to include these three fields.

**New request schemas:**

```python
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)

class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10)
```

---

### Modified: `backend/app/api/auth.py`

New endpoints (all under `/auth` prefix):

```
POST /auth/password/forgot
  Body: ForgotPasswordRequest
  Response: 202 { "detail": "If that email is registered, a reset link is on its way." }
  — Always 202 (non-enumeration). Rate-limited per email key (same LoginRateLimiter pattern, separate instance: reset_rate_limiter = LoginRateLimiter(max_attempts=3, window_seconds=3600)).
  — Creates AuthToken(type="password_reset"), sends reset email async (fire-and-forget; errors logged, not raised).

POST /auth/password/reset
  Body: ResetPasswordRequest
  Response: 200 MeResponse  (issues session cookie on success — user is logged in after reset)
  — Looks up AuthToken by SHA256(token). Validates: found, type=="password_reset", not used, not expired.
  — Sets user.password_hash = hash_password(new_password), user.password_changed_at = now().
  — Marks token used (used_at = now()).
  — Does NOT invalidate existing sessions (stateless JWT). Design decision: JWT sessions are short-lived (30 days) and there is no token blocklist. Add to Open Questions if the user wants session invalidation.
  — Calls set_auth_cookie(response, user.id) and returns full MeResponse.

POST /auth/password/change    (requires auth)
  Body: ChangePasswordRequest
  Response: 204
  — Requires user.password_hash IS NOT NULL (else 400 "No password set on this account — use set-password instead").
  — Verifies current_password against stored hash.
  — Rejects if new_password == current_password (400 "New password must differ from current").
  — Sets password_hash, password_changed_at. Does not invalidate session.

POST /auth/password/set       (requires auth)
  Body: SetPasswordRequest
  Response: 204
  — Requires user.password_hash IS NULL (else 400 "Account already has a password — use change-password instead").
  — Requires user.email IS NOT NULL (else 400 "An email address is required to set a password").
  — Sets password_hash, password_changed_at.

POST /auth/email/resend-verification   (requires auth)
  Response: 202 { "detail": "Verification email sent." }
  — Rate-limited: verify_rate_limiter = LoginRateLimiter(max_attempts=3, window_seconds=3600), keyed by user.id.
  — Requires user.email IS NOT NULL and user.email_verified IS FALSE (else 400).
  — Creates AuthToken(type="email_verify"), sends verification email async.

GET /auth/email/verify
  Query: token: str
  Response: 204
  — Looks up AuthToken by SHA256(token). Validates: found, type=="email_verify", not used, not expired.
  — Sets user.email_verified = True, marks token used.
  — Does not re-issue session cookie (user may or may not be logged in when clicking the link — both work).
```

**`signup` endpoint modification:**

After commit, fire-and-forget: create `AuthToken(type="email_verify")` and send verification email. Do not await the send in the request path; schedule it as a background task (`BackgroundTasks` from FastAPI is appropriate here).

---

### New: `backend/alembic/versions/010_auth_tokens_and_email_verified.py`

```
revision = "010"
down_revision = "009"

upgrade():
  - add_column "users": email_verified (Boolean, NOT NULL, server_default 'false')
  - add_column "users": password_changed_at (DateTime(tz=True), nullable)
  - create_table "auth_tokens": (see model above)
  - create_index on auth_tokens(user_id, token_type)
  - create_index on auth_tokens(token_hash) [unique covered by column constraint]

downgrade():
  - drop_table "auth_tokens"
  - drop_column "users" "password_changed_at"
  - drop_column "users" "email_verified"
```

Note: existing users will have `email_verified = false` after migration. Users who authenticated via Google/Yahoo (where `email_verified` was true at OAuth time) should ideally be flipped to `true`. However, that backfill is complex (requires re-reading `yahoo_email_verified` state, which we didn't persist). Decision: do not backfill. OAuth users who see the banner can dismiss it. If this is disruptive, a follow-up migration can target rows where `google_subject IS NOT NULL OR yahoo_subject IS NOT NULL` and set `email_verified = true` — but this is deferred to a separate issue (see Out of Scope).

---

### Modified: `backend/app/config.py`

Add:
```python
ses_from_address: str = "AutoTiers <noreply@autotiers.com>"
ses_region: str = "us-east-1"
email_sender_backend: str = "ses"  # "ses" | "fake"
```

When `email_sender_backend == "fake"` (or `debug == True`), the app uses `FakeSender` that prints to stdout. This is the default in development so no SES credentials are needed locally.

---

### Frontend: new/modified files

**`web/src/api/auth.ts`** — add:

```typescript
export interface ForgotPasswordBody { email: string; }
export interface ResetPasswordBody { token: string; new_password: string; }
export interface ChangePasswordBody { current_password: string; new_password: string; }
export interface SetPasswordBody { new_password: string; }

export function requestPasswordReset(body: ForgotPasswordBody): Promise<void>
export function confirmPasswordReset(body: ResetPasswordBody): Promise<MeResponse>
export function changePassword(body: ChangePasswordBody): Promise<void>  // 204
export function setPassword(body: SetPasswordBody): Promise<void>         // 204
export function resendVerificationEmail(): Promise<void>                   // 202
export function verifyEmail(token: string): Promise<void>                 // 204
```

**`web/src/api/types.ts`** — add to `User` interface:

```typescript
has_password: boolean;
email_verified: boolean;
password_changed_at: string | null;  // ISO 8601
```

**`web/src/contexts/AuthContext.tsx`** — no structural changes needed. `refresh()` already re-fetches `/api/auth/me` and updates the `user` object. New fields will flow through automatically.

**`web/src/components/AuthDialog.tsx`** — significant update:

New internal view state: `"login" | "signup" | "forgot_password_request" | "forgot_password_sent"`. Default `"login"`.

States:
- `"login"`: existing form + "Forgot password?" link below password field.
- `"signup"`: existing form + confirm-password field + show/hide toggles + strength hint.
- `"forgot_password_request"`: single-field form with email. "Back to log in" link.
- `"forgot_password_sent"`: static success message. "Back to log in" link.

The `Tabs` component drives `"login"` vs `"signup"`. The forgot-password sub-views replace the tab content area when active (tabs remain visually present but the content area renders the forgot-password form instead of the tab panels). Switching tabs resets to the tab's default state (clears forgot-password state).

Show/hide toggle: `Eye` / `EyeOff` icons from `lucide-react` (already a dep). The button sits inside the input container (relative positioning; the icon is absolutely positioned right-inset). Use `aria-label` on the toggle button. The input's `type` is controlled state.

**`web/src/components/PasswordManagementSection.tsx`** — new component:

Renders inside `LinkedAccountsDialog.tsx` as a new section at the bottom (below the Google footer row — or as a separate tab if the dialog already has tabs; see placement note below).

Props:
```typescript
interface Props {
  user: User;
  onRefresh: () => Promise<void>;
}
```

Placement note: `LinkedAccountsDialog` currently has a platform-tab strip (Sleeper/ESPN/Yahoo/NFL/CBS) and a Google footer. The password section is not a "platform connection" — it should appear below the Google footer as a separate horizontal section with its own border-top. Alternatively, it could be a dedicated "Account" section at the top of the dialog (above the tab strip). Design choice: **place it above the tab strip as an "Account" section**. This makes the dialog's two concerns explicit — "Account credentials" (password row) and "Fantasy leagues" (platform tabs). The Google row moves to sit adjacent to the password row in the Account section.

Updated `LinkedAccountsDialog` layout:

```
┌─ Connect Your League ────────────────────────────────┐
│                                                       │
│  Account                                              │
│  ┌──────────────────────────────────────────────┐    │
│  │ Email  user@example.com    [Change password]  │    │
│  │ Google · sign-in only     [Link] / [Unlink]   │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  Fantasy leagues                                      │
│  [Sleeper] [ESPN] [Yahoo] [NFL▾] [CBS▾]               │
│  ┌──────────────────────────────────────────────┐    │
│  │  (tab panel content)                          │    │
│  └──────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────┘
```

The "Change password" / "Set password" button expands an inline form below the email row (accordion-style). Only one expansion is active at a time.

**`web/src/App.tsx`** — query-param handling:

Add to the existing `useEffect` that reads OAuth query params:

```typescript
const resetToken = params.get("reset_token");
const verifyToken = params.get("verify_token");
```

- If `reset_token` present: set `resetToken` state; strip param from URL. Render `<PasswordResetPanel token={resetToken} />` above main content (same slot as onboarding card).
- If `verify_token` present: immediately call `verifyEmail(token)`, strip param; show toast on success/failure.

**`web/src/components/PasswordResetPanel.tsx`** — new component:

Renders as a full-width card between Header and main content grid when a `reset_token` is in state. Not a dialog — it's inline so the user can see the full app context.

States:
- Loading (token present, not yet validated — token is validated at submit time, not on load): shows the form immediately.
- Form: new password + confirm password + show/hide + strength hint + submit.
- Success: confirmation message + auto-redirects to logged-in state.
- Error (expired/used/invalid): error message + "Request new link" button.

**`web/src/components/EmailVerificationBanner.tsx`** — new component:

Props:
```typescript
interface Props {
  email: string;
  onResend: () => Promise<void>;
  onDismiss: () => void;
}
```

Renders as a dismissible yellow banner. `role="status"` on the container. The resend button has a loading state (spinner + "Sending..."). After successful resend, the banner text changes to "Verification email sent. Check your inbox." for 3 seconds then the banner hides.

**`web/src/components/Header.tsx`** — minor: no change needed. The banner slot is in `App.tsx` above `<main>`.

---

### Session invalidation on password reset

Design decision: **do not invalidate existing JWT sessions on password reset**. Rationale:
1. JWTs are httpOnly and short-lived (30 days). Token theft requires server-side compromise — rate limiting on the reset endpoint is a more practical defense.
2. Implementing a token blocklist requires Redis or a database round-trip on every authenticated request — a disproportionate cost for the current single-container deployment.
3. The "cannot unlink last sign-in method" invariant is not affected by this decision.

If the user's account is compromised and they reset their password, any attacker sessions will expire within 30 days. This is the standard tradeoff for stateless JWT auth without a blocklist.

---

### "Cannot unlink last sign-in method" invariant — impact analysis

The `_has_other_method` helper checks:
- `"password"`: `user.password_hash is not None`
- `"yahoo_subject"`: not None
- `"google_subject"`: not None

**Set password (Slice C):** adds `password_hash`, so after this operation the user always has at least two methods (the OAuth they used plus the new password). No conflict.

**Change password (Slice B):** updates `password_hash` without clearing it. Invariant unaffected.

**Reset password (Flow A):** sets `password_hash` if not already set; updates it if it was. Invariant unaffected (password method now exists).

No changes to the unlink endpoints are required.

---

## Implementation slices (ordered, independently shippable)

### Slice 1 — Data model + migration
Files: `backend/app/models/auth_token.py`, `backend/app/models/user.py`, `backend/alembic/versions/010_auth_tokens_and_email_verified.py`, `backend/app/models/__init__.py`, `backend/app/schemas/auth.py` (UserOut extension only).

Produces: migration that can be applied to staging. No behavior change yet.

### Slice 2 — Email sender abstraction
Files: `backend/app/email/` (all four files), `backend/app/config.py`, `backend/app/main.py` (wiring).

Produces: injectable `EmailSender`. FakeSender used in all environments until SES creds land. Covered by unit tests that verify `FakeSender.sent` after calls.

### Slice 3 — Forgot password (backend)
Files: `backend/app/api/auth.py` (new `POST /auth/password/forgot` and `POST /auth/password/reset`), `backend/app/schemas/auth.py` (new request schemas), `backend/app/email/templates.py` (reset email template).

Produces: working API endpoints, testable without frontend.

### Slice 4 — Email verification (backend)
Files: `backend/app/api/auth.py` (new `POST /auth/email/resend-verification`, `GET /auth/email/verify`, signup modification), `backend/app/email/templates.py` (verification email template).

Produces: working API endpoints. Signup now sends a verification email (background task, silently fails if FakeSender is in use).

### Slice 5 — Change/set password (backend)
Files: `backend/app/api/auth.py` (new `POST /auth/password/change`, `POST /auth/password/set`).

Produces: working API endpoints for authenticated password management.

### Slice 6 — Frontend
Files: `web/src/api/auth.ts`, `web/src/api/types.ts`, `web/src/components/AuthDialog.tsx`, `web/src/components/PasswordManagementSection.tsx`, `web/src/components/PasswordResetPanel.tsx`, `web/src/components/EmailVerificationBanner.tsx`, `web/src/App.tsx`.

Produces: complete user-facing flows. Can be developed in parallel with Slices 3–5 using mocked API responses, then integrated.

---

## Math / statistical claims

N/A. No scoring formula, weight, or ranking algorithm is affected by this feature.

---

## FF heuristic basis

N/A. This feature is authentication infrastructure.

---

## Out of scope

- **Backfilling `email_verified = true` for existing OAuth users.** Deferred — current OAuth users will see the verification banner but can dismiss it. File a follow-up issue.
- **Session invalidation on password reset** (token blocklist / Redis). Explicitly decided against for now. File a follow-up issue to revisit when the deployment goes multi-instance.
- **Magic-link (passwordless) login.** Not requested. The email infrastructure built here would enable it cheaply in the future — file a future-work issue.
- **Two-factor authentication (TOTP/SMS).** Not requested.
- **"Remember this device" / extended session.** Not in scope.
- **Admin-initiated password reset.** The admin API key exists but password management for admin is out of scope.
- **Password history enforcement** (prevent reuse of last N passwords). Not requested.
- **Email change flow** (user wants to update their email address). The current data model supports this but the UI and verification re-send logic are not designed here.
- **Email-based account merge** (two accounts share a verified email). The existing OAuth signup already handles the "same email, auto-link" case. No change needed here.

---

## Open questions

1. **Should a successful password reset invalidate all existing sessions?** The design defaults to No (stateless JWT, no blocklist). If the user wants Yes, the Engineer needs a `token_version` column on `User` included in the JWT payload — a small migration and a middleware check. Cost: one extra DB read per authenticated request. Recommend: leave No for now; revisit when multi-instance.

2. **Email verification: should any feature be gated on `email_verified`?** The design defaults to soft (no gate). If the user wants hard gating (e.g., block "generate tiers" for unverified users), that can be added as a thin backend check on the existing gate point. Recommend: soft for now — hard gating is disruptive to the existing zero-friction experience.

3. **SES sender domain/address:** the spec uses `noreply@autotiers.com`. Confirm the sending identity to verify in SES and the `SES_FROM_ADDRESS` value before Slice 2 ships to production.

4. **Rate limiter limits for reset/verify:** proposed `max_attempts=3, window_seconds=3600` (3 reset emails per hour per email address). Confirm or adjust based on expected user volume. The login limiter is `max_attempts=5, window_seconds=900`.

5. **Password reset: should the new password also implicitly verify the user's email?** Argument: if a user clicked a link sent to their inbox, they've demonstrated inbox control — this is equivalent to email verification. Design defaults to Yes: a successful password reset also sets `email_verified = True`. State this explicitly in the implementation.
