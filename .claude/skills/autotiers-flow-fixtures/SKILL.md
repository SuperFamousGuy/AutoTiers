---
name: autotiers-flow-fixtures
description: Concrete curl + sqlite/psql snippets to exercise the major AutoTiers flows end-to-end. Invoke when a change needs manual verification beyond the test mocks — auth flows, OAuth, league linking, and generate. The QA agent uses these to actually drive the running container rather than just inspect code.
---

# Driving AutoTiers flows by hand

The backend listens on `http://localhost:8000` when run via `podman compose up`. The frontend hits it from `http://localhost:5173`. All examples assume that setup.

The session cookie is `autotiers_session` (httponly, SameSite=lax). For curl, persist it in a jar:

```bash
COOKIES=/tmp/autotiers-cookies.txt
```

## Signup → log-in → /me

```bash
# Signup
curl -sS -c $COOKIES -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"qa@example.com","password":"password-long-enough"}' | python3 -m json.tool

# Confirm authenticated
curl -sS -b $COOKIES http://localhost:8000/api/auth/me | python3 -m json.tool

# Log out
curl -sS -b $COOKIES -X POST http://localhost:8000/api/auth/logout -o /dev/null -w "%{http_code}\n"
# → 204
```

To test the "user with active session" scenarios, keep `$COOKIES` populated. To test "no session," omit `-b $COOKIES`.

## Probe signup error shapes

```bash
# Email already in use → expect 409 with {detail: "Email already in use"}
curl -sS -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"qa@example.com","password":"password-long-enough"}' | python3 -m json.tool

# Password too short → expect 422 with detail[] array
curl -sS -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com","password":"short"}' | python3 -m json.tool

# Bad email → expect 422
curl -sS -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"not-an-email","password":"password-long-enough"}' | python3 -m json.tool
```

## Profile CRUD

```bash
# After login, get your profiles
curl -sS -b $COOKIES http://localhost:8000/api/auth/me | python3 -c "import json,sys; d=json.load(sys.stdin); print([p['id'] for p in d['profiles']])"

# Create
curl -sS -b $COOKIES -X POST http://localhost:8000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","settings_json":{},"rules_json":[]}' | python3 -m json.tool

# PATCH (autosave)
PROFILE_ID=<paste-from-above>
curl -sS -b $COOKIES -X PATCH "http://localhost:8000/api/profiles/$PROFILE_ID" \
  -H "Content-Type: application/json" \
  -d '{"settings_json":{"scoring_format":"ppr"},"rules_json":[]}' | python3 -m json.tool
```

## Linked-league flows

```bash
# Sleeper full link (real Sleeper API call — needs internet)
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/sleeper" \
  -H "Content-Type: application/json" \
  -d '{"username":"some_real_sleeper_user","league_id":"<id>","season":2026}' | python3 -m json.tool

# Sleeper pre-link (no league)
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/sleeper" \
  -H "Content-Type: application/json" \
  -d '{"username":"some_real_sleeper_user"}' | python3 -m json.tool

# ESPN reject-empty validation → expect 400
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/espn" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# ESPN public league
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/espn" \
  -H "Content-Type: application/json" \
  -d '{"league_id":"<id>","season":2026}' | python3 -m json.tool

# ESPN private league with cookies
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/espn" \
  -H "Content-Type: application/json" \
  -d "{\"league_id\":\"<id>\",\"season\":2026,\"swid\":\"$REAL_SWID\",\"espn_s2\":\"$REAL_S2\"}" | python3 -m json.tool

# Refresh
curl -sS -b $COOKIES -X POST "http://localhost:8000/api/profiles/$PROFILE_ID/link/refresh" | python3 -m json.tool

# Disconnect
curl -sS -b $COOKIES -X DELETE "http://localhost:8000/api/profiles/$PROFILE_ID/link" -o /dev/null -w "%{http_code}\n"
# → 204
```

## OAuth (Yahoo / Google) — manual browser only

The redirect chain requires a real browser session. Manual checklist:

1. While logged in, click **Connect Yahoo** in the dialog. Verify the URL navigated to is `/api/auth/yahoo/authorize?intent=link` (the `intent=link` part is the recent fix; without it the callback can silently create a new user).
2. After signing into Yahoo, the browser lands on `frontend_url`. Check `Application > Cookies` for:
   - `autotiers_session` (existing, unchanged)
   - `autotiers_oauth_state` (just deleted by the callback)
   - `autotiers_oauth_intent` (just deleted by the callback)
3. Open the dialog again. Verify the Yahoo row now shows **Disconnect** and your existing profiles + linked leagues are still present.

### Inducing the session-lost scenario

In DevTools, before clicking Connect, delete the `autotiers_session` cookie. Click Connect. After Yahoo bounces you back, you should land at `frontend_url?linking_error=session_lost` and see the dialog open with *"Your sign-in session was lost during the redirect…"*. A new user must NOT have been created. Verify:

```sql
-- Run inside the db container
SELECT id, email, yahoo_subject FROM users ORDER BY created_at DESC LIMIT 3;
```

No new row for the Yahoo subject you just signed in with.

## Database inspection

Inside the `db` container:

```bash
podman exec -it autotiers-db psql -U postgres -d autotiers

# Inside psql:
\dt linked_leagues   -- describe the table
SELECT profile_id, provider, league_id, league_metadata_json FROM linked_leagues;
SELECT id, email, yahoo_subject, google_subject FROM users;
\dt profiles
SELECT id, user_id, name, last_active_profile_id FROM profiles;
```

Use this to verify persistence claims that test mocks can't validate. Common checks after a link flow:

- LinkedLeague row exists with the expected provider and league_id (or NULL for pre-link).
- `credentials_encrypted` is non-NULL and clearly not equal to the plaintext espn_s2 the user typed (the encryption is doing its job).
- After Disconnect, the row is gone (no soft-delete cruft).

## What this skill is for

This is the difference between "the tests pass" and "the flow actually works in the running app." Most of the recent bugs (phantom user, URL-encoded cookies, empty-form-linked) would have been caught by a 30-second curl session. The QA agent should default to running at least one of these when a change touches the corresponding flow.
