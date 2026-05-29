# Account Linking + OAuth Email Dedupe — Design

## Goal

Let signed-in users link Yahoo and/or Google to their existing account, and stop "Continue with Google / Yahoo" from creating a duplicate account when the OAuth-returned email already belongs to an existing user.

## Background

Today, `User` carries `email`, `password_hash`, `yahoo_subject`, and `google_subject` columns. OAuth flows match strictly on `*_subject` and create a new user when no match is found. To avoid an email-collision takeover risk, we deliberately did not request `email` scope. As a result, signing up with `a@b.com` and then later clicking "Continue with Google" with the same Google-side email produces two separate accounts.

## Design decisions (locked)

- **Email dedupe policy:** auto-link on `email_verified == true`. Both Google and Yahoo's OIDC implementations expose this claim and we treat it as trustworthy.
- **Linking UI location:** new "Linked accounts" item in the existing hamburger menu, opening a dialog.
- **Unlinking:** allowed, but server rejects the request if it would leave the user with zero sign-in methods.
- **Existing duplicate accounts:** forward-only fix — we do not build a merge flow.

## Architecture

The OAuth callback gains a link-vs-signin branch based on whether the request already carries a valid auth cookie. Both providers expand their OAuth scope to `openid email`. `fetch_subject` is replaced with `fetch_identity` returning `(subject, email, email_verified)`.

No database migration is required — `User` already has every column we need.

## Backend changes

### `app/auth/google.py` and `app/auth/yahoo.py`

- Scope becomes `openid email` (Google) and the Yahoo equivalent.
- `fetch_subject(access_token) -> str` is replaced with `fetch_identity(access_token) -> tuple[str, str | None, bool]` returning `(subject, email, email_verified)`. `email` may be `None` if the provider declines to return one; `email_verified` defaults to `False` if absent.

### `app/api/auth.py` — callback handlers

Both `/yahoo/callback` and `/google/callback` apply the same logic:

1. Exchange code → `(subject, email, email_verified)`.
2. Attempt to resolve the current user from the existing auth cookie (without raising on absence).
3. Branch on auth state:

   **Authenticated request (linking flow):**
   - Subject already on this user → no-op; redirect home.
   - Subject already on a different user → redirect home with `?linking_error=already_linked_elsewhere`. (The callback is a browser-driven GET that always returns a `RedirectResponse`, so we surface the failure via query param rather than a JSON error.)
   - Subject not on any user → attach subject to current user. If current user has no email and `email_verified`, backfill `email` from the provider.

   **Unauthenticated request (sign-in flow):**
   - Subject matches an existing user → set auth cookie, redirect home.
   - No subject match, `email_verified` is true, and email matches an existing user → attach subject to that user (auto-link, the dedupe fix), set cookie, redirect home.
   - No match anywhere → create a new user. Set `email` only if `email_verified`. Attach subject. Set cookie, redirect home.

### New endpoints

- `DELETE /api/auth/yahoo/link` (auth required) — null `current_user.yahoo_subject`.
- `DELETE /api/auth/google/link` (auth required) — null `current_user.google_subject`.

Both reject with `400 Bad Request` and detail `"Cannot unlink last sign-in method"` if the unlink would leave the user with no remaining method (i.e. `password_hash is None` and the other `*_subject` is also `None`).

### `MeResponse`

No shape change. The frontend already receives `email`, `yahoo_subject`, `google_subject` and can derive connected state from null vs. non-null.

## Frontend changes

### `web/src/components/LinkedAccountsDialog.tsx` (new)

Rows:

- **Email** — read-only label showing `user.email`, or "Not set" if null.
- **Google** — "Connected" + Disconnect button, or "Not connected" + Connect button. Connect navigates to `googleAuthorizeUrl()` (full-page redirect — the OAuth flow returns to the app). Disconnect calls `DELETE /api/auth/google/link` then refreshes `/me`.
- **Yahoo** — same shape as Google.

Connected state is derived purely from the `/me` payload (`user.google_subject != null`, etc.). After Connect completes, the OAuth callback redirects back to the app and the existing `/me` query refetch picks up the new state.

### `web/src/components/Header.tsx`

Add a "Linked accounts" `<DropdownMenuItem>` between the user-email row and "Log out". Opens the dialog.

### `web/src/api/auth.ts`

Add:

- `unlinkYahoo(): Promise<void>` — `DELETE /api/auth/yahoo/link`, throws `ApiError` on non-2xx.
- `unlinkGoogle(): Promise<void>` — same for Google.

Authorize URLs (`yahooAuthorizeUrl`, `googleAuthorizeUrl`) are unchanged — the backend callback handles link vs. sign-in via the cookie.

### Linking-error toast

On app mount, check the URL for `?linking_error=already_linked_elsewhere`. If present, show a toast (`"This Google/Yahoo account is already linked to a different AutoTiers account."`) and strip the query param via `history.replaceState`.

## Edge cases

- **Pre-existing OAuth users with no email:** next sign-in backfills `email` if `email_verified`. Non-breaking.
- **Same email used at both providers by the same person:** first provider creates the user; the second provider's sign-in auto-links by email match — no duplicate.
- **Email changes at provider:** we do not overwrite the stored email on subsequent OAuth sign-ins. The subject column is the stable identifier.
- **`email_verified` absent or false:** falls through to subject-only behavior. Sign-in by subject still works, but no auto-link.
- **Pre-existing duplicate accounts (created before this fix):** untouched. The forward-only fix means these stay as separate accounts until a future merge feature is built.
- **User links Google whose email matches yet another existing account:** since we are authenticated, we attach the subject to the current user. We deliberately do not try to detect or merge the other account — that's a duplicate-merge concern, explicitly out of scope.

## Testing

### Backend (pytest, mocking `httpx` for token exchange + userinfo)

Each provider gets the same matrix:

- Subject match → existing user signed in.
- No subject match, `email_verified=True`, email matches existing user → subject attached, signed in.
- No subject match, `email_verified=False`, email matches existing user → new user created (not auto-linked).
- No match anywhere → new user created; email set only if verified.
- Authenticated request, subject not yet linked → attached to current user.
- Authenticated request, subject already linked to current user → no-op (200, no DB change).
- Authenticated request, subject linked to different user → redirect with `linking_error` param.
- `DELETE /link` with another method present → succeeds, column nulled.
- `DELETE /link` as last method → rejected 400.
- `DELETE /link` unauthenticated → 401.

### Frontend (vitest + MSW)

- `LinkedAccountsDialog` renders correct connected/not-connected state from a `/me` payload.
- Disconnect button calls the correct DELETE endpoint; success refetches `/me`.
- Disconnect that returns 400 shows the "last method" error in the dialog (not a crash).
- Hamburger menu shows "Linked accounts" item only when authenticated.
- App mount with `?linking_error=already_linked_elsewhere` shows toast and strips the param.

## Not doing (YAGNI)

- Merging existing duplicate accounts.
- Forgot-password / account-recovery flow.
- Email-change flow.
- Persisting `email_verified` on `User` (used at link/sign-in time only).
- Showing OAuth-side emails alongside the user's primary email in the dialog. Single email per account, period.
