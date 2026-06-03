---
name: autotiers-ff-knowledge
description: Structured catalogue of fantasy football heuristics with sources, confidence ratings, and implementation status in AutoTiers. Invoke when scoping a new rule, validating an existing rule in `backend/app/engine/builtin_rules.py`, or briefing a non-FF-native agent on the conventional wisdom (and its limits) for a position or strategy. Curated by the autotiers-researcher agent.
---

# AutoTiers fantasy football knowledge base

Each entry is one heuristic. Read the source links before relying on it — confidence ratings are a guide, not a substitute.

## How to use this file

- **Scoping a new rule?** Search by position or theme. Each entry's "Implementation status" line tells you whether the rule already exists.
- **Validating an existing rule?** Find the entry whose "Implementation status" points at the rule file. The "Sources" section is the audit trail.
- **Adding a new entry?** Use the template at the bottom of this file. Keep entries terse. Cite sources with author + year + URL.

## Currently shipped rules (cross-reference)

These rules exist in `backend/app/engine/builtin_rules.py`. Researcher entries should reference them by name when relevant:

- **"370 Touches"** — high-volume RB workload curse, penalizes RBs with prior-season touches above a threshold.
- **"Year After the Year After"** — post-breakout regression for receivers two seasons after a sudden leap.
- **"Bad Offense"** — penalty for skill-position players on low-projected-points teams.
- **"Follow the Money"** — uses free-agent contract size as a signal for target/touch share at the new team.

When research validates, refines, or contradicts one of these, say so in the entry's "Implementation status" line.

## Entries

<!-- Researcher: append entries here, one per heuristic, using the template below. Keep newest at the top. -->

---

### ESPN API Base URL Stale (fantasy.espn.com → lm-api-reads.fantasy.espn.com)

- **Claim (operational form):** ESPN migrated its Fantasy Football API base domain from `fantasy.espn.com` to `lm-api-reads.fantasy.espn.com` in April 2024; requests to the old domain now fail or redirect rather than returning JSON for private leagues.
- **Position(s) / league type(s):** Platform/infrastructure concern — applies to all ESPN league types (public and private) regardless of scoring format or sport.
- **Reasoning:** Multiple independent sources (Steven Morse blog update, ESPN hidden API gist comments, Zuplo developer guide) all document that ESPN changed the base URL without notice around April 2024. The old `fantasy.espn.com/apis/v3/games/ffl/...` path broke existing integrations overnight. The new canonical path is `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/...`. AutoTiers currently hardcodes the old domain in two places: `backend/app/integrations/espn.py` (`_BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"`) and `backend/app/data/sources/espn.py` (`base_url = "https://fantasy.espn.com"`). The `integrations/espn.py` client already handles 3xx redirects as an auth failure, which means a silent redirect from the old to the new host would surface to users as "ESPN rejected the request — league may be private" rather than a connectivity error — a deeply misleading error message.
- **Sources:**
  - Steven Morse, 2024, "Using ESPN's new Fantasy API (v3)" — https://stmorse.github.io/journal/espn-fantasy-v3.html — credibility: medium (practitioner blog with reproducible code, editorial note explicitly added post-migration)
  - akeaswaran / multiple contributors, 2024, ESPN hidden API Docs gist comment thread — https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b?permalink_comment_id=5186770 — credibility: medium (community-maintained, corroborated by independent sources)
  - Zuplo, 2024, "Unlocking ESPN's Hidden API: a Developer's Guide" — https://zuplo.com/learning-center/espn-hidden-api-guide — credibility: medium (developer-oriented, names the April 2024 migration explicitly)
- **Disagreements / counterevidence:** Some sources (including the ESPN Cookie Finder extension description from August 2025) still describe the flow as targeting `fantasy.espn.com` without noting any issue, suggesting the old domain may still proxy requests for some endpoints. However, this is insufficient counter-evidence to rely on — the migration is corroborated by too many independent reports, and AutoTiers' existing redirect-as-auth-failure logic would mask the breakage.
- **Confidence:** high — three independent sources converge on the same domain change and the same approximate date. The AutoTiers codebase independently confirms the old URL is still hardcoded.
- **Implementation status:** not implemented — AutoTiers `backend/app/integrations/espn.py` and `backend/app/data/sources/espn.py` both still use `https://fantasy.espn.com`. This is a latent bug, not a heuristic; it does not belong in `builtin_rules.py`.
- **Suggested next step:** Update `_BASE_URL` in `backend/app/integrations/espn.py` to `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl` and `base_url` in `backend/app/data/sources/espn.py` to `https://lm-api-reads.fantasy.espn.com`; also remove the redirect-as-auth-failure guard or at minimum log the redirect target before raising `EspnAuthRequired`.

---

### ESPN Has No Official OAuth for Fantasy Leagues — Cookie-Based Auth Is the Only Path

- **Claim (operational form):** ESPN does not expose a developer OAuth program for Fantasy Football; SWID + espn_s2 session cookies extracted from a logged-in browser are the only programmatic access method for private leagues, and this is confirmed working as of August 2025.
- **Position(s) / league type(s):** Platform/auth concern — applies to all private ESPN league types across all sports. Public leagues require no authentication.
- **Reasoning:** No ESPN developer portal, OAuth 2.0 endpoint, or API key registration flow exists for Fantasy Football (confirmed by absence across all searched documentation and developer resources as of June 2026). ESPN added reCAPTCHA to login pages, explicitly blocking username/password programmatic auth. The two undocumented session cookies — `SWID` (a UUID in curly braces, ~38 chars) and `espn_s2` (an opaque blob, typically 200+ chars) — are the accepted workaround. These are persistent cookies tied to the ESPN account, not ephemeral session tokens; they survive browser restarts. Multiple libraries (cwendt94/espn-api v0.46.0 as of March 2026, ffscrapr, mkreiser/ESPN-Fantasy-Football-API) and tools (FantasyPros, GameDayBot, ffverse) all implement this same pattern. FantasyPros explicitly stores an "encrypted ESPN cookie on their servers" for periodic re-sync, demonstrating this is production-grade practice at scale.
- **Sources:**
  - cwendt94/espn-api Discussion #150, 2020–2025 (ongoing) — https://github.com/cwendt94/espn-api/discussions/150 — credibility: medium (high-volume community thread, consistent across years)
  - ffscrapr / ffverse, 2024, "ESPN: Private Leagues" — https://ffscrapr.ffverse.com/articles/espn_authentication.html — credibility: high (well-maintained R package with explicit "cannot be done programmatically" statement)
  - FantasyPros Support, 2024, "How do I add my ESPN fantasy league?" — https://support.fantasypros.com/hc/en-us/articles/360051313453 — credibility: high (production SaaS product explicitly describing their server-side cookie storage pattern)
  - ESPN Cookie Finder Chrome extension, v1.2 updated August 25, 2025 — https://chromewebstore.google.com/detail/espn-cookie-finder/oapfffhnckhffnpiophbcmjnpomjkfcj — credibility: medium (active maintenance into 2025/2026 season confirms the method is not deprecated)
- **Disagreements / counterevidence:** None. Every source surveyed — from casual Reddit posts to production tools — lands on the same method. ESPN's silence on an official API is itself evidence that no alternative exists.
- **Confidence:** high — universal convergence across high- and medium-credibility sources spanning 2020–2026.
- **Implementation status:** implemented — `backend/app/integrations/espn.py` and `backend/app/api/linked_league.py` implement exactly this pattern. The finding validates the approach but does not change the codebase.
- **Suggested next step:** No rule change needed. The finding constrains UX options: any improvement must work within the cookie-extraction paradigm (see entries below).

---

### SWID Cookie Format Confusion Is a Recurring Auth Failure Source

- **Claim (operational form):** The ESPN SWID cookie value must be pasted with its surrounding curly braces (e.g. `{ABCD-1234-...}`); omitting them produces a 401/403 from ESPN, and users regularly make this mistake because DevTools does not visually distinguish delimiters from value.
- **Position(s) / league type(s):** Platform/auth UX concern — private ESPN leagues only.
- **Reasoning:** The cwendt94/espn-api GitHub issue #549 and Discussion #150 both document user confusion specifically around whether the curly braces are part of the SWID value. The AutoTiers backend already handles this correctly by constructing the Cookie header as a raw string (`SWID={swid}`) rather than URL-encoding through httpx's Cookies object (which would mangle the braces). However, the frontend form that accepts SWID input has no visual annotation or validation to confirm the braces are present, leaving users who copy only the UUID interior to fail silently.
- **Sources:**
  - cwendt94/espn-api Issue #549, 2024 — https://github.com/cwendt94/espn-api/issues/549 — credibility: medium (reproducible user report with technical detail)
  - cwendt94/espn-api Discussion #150, 2020–2025 — https://github.com/cwendt94/espn-api/discussions/150 — credibility: medium
  - You Suck at Fantasy Football cookie instructions, 2024 — https://www.yousuckatfantasyfootball.com/instructions — credibility: low (but one of the clearest user-facing guides; describes SWID as "a shorter string that looks like {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}")
- **Disagreements / counterevidence:** None. All sources agree on the format requirement.
- **Confidence:** high — the format requirement is consistent and the failure mode is well-documented.
- **Implementation status:** not implemented as a validation rule in `builtin_rules.py` (this is a UX/validation concern, not a fantasy scoring heuristic). Backend correctly constructs the raw cookie header. Frontend input validation for `{...}` format is not confirmed.
- **Suggested next step:** Add client-side validation on the SWID input field that checks for leading `{` and trailing `}` and shows an inline hint ("Include the curly braces — your SWID should look like {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"). Also add a server-side check in `post_espn` that returns a 400 with this message if the SWID is present but lacks braces.

---

### Browser Extension Is the Lowest-Friction Cookie Extraction Method for Non-Technical Users

- **Claim (operational form):** A browser extension that reads ESPN cookies and displays them for copy-paste reduces DevTools-based cookie extraction errors to near zero; this is the approach independently chosen by FantasyPros, PFF, GameDayBot, and Flock Fantasy — it is the industry-standard UX pattern for this problem as of 2025–2026. IMPORTANT CAVEAT: as of Chrome 138 (July 2025) all Manifest V2 extensions are disabled; any extension not migrated to Manifest V3 is now non-functional on Chrome.
- **Position(s) / league type(s):** Platform/UX concern — private ESPN leagues, all scoring formats.
- **Reasoning:** Five independent actors reached the same UX solution: (1) FantasyPros — Chrome extension (MV3) that extracts and transmits the ESPN cookie server-side; (2) PFF — "PFF for your Fantasy League" extension (MV3, v1.0, last updated August 4 2025, ~9,000 users, 5.0 stars); (3) GameDayBot — "ESPN Private League Setup" (MV3, v2.0, last updated August 20 2025, 392 users); (4) Flock Fantasy — "ESPN Quick Sync" (MV3, v1.1.1, August 2024, ~20,000 users, 2.8 stars — documented sync failures requiring the user to open ESPN in the same browser first); (5) Hashtag Fantasy Sports — "ESPN Cookie Finder" (v1.2, updated August 25 2025) — STATUS UNKNOWN: sources confirm this extension was still on Manifest V2 as of the August 2025 update; Chrome 138 disabled all MV2 extensions, and Chrome 139 removes support entirely. The Firefox add-on remains valid (Firefox has its own MV3 rollout timeline). All working extensions use `chrome.cookies.get()` in a background script — this API reads cookies including those marked HttpOnly, which `document.cookie` cannot. For a web product like AutoTiers that cannot ship a browser extension, the only remaining option is a guided in-app flow with annotated screenshots. Pointing users to a specific third-party extension carries risk because extension status changes between football seasons.
- **Sources:**
  - ESPN Cookie Finder (Chrome), Hashtag Fantasy Sports, v1.2 August 25 2025 — https://chromewebstore.google.com/detail/espn-cookie-finder/oapfffhnckhffnpiophbcmjnpomjkfcj — credibility: medium; MV2 status confirmed via chrome-stats.com listing; reliability on Chrome 138+ unknown
  - ESPN Cookie Finder (Firefox), Hashtag Fantasy Sports — https://addons.mozilla.org/en-US/firefox/addon/espn-cookie-finder/ — credibility: medium (Firefox add-on unaffected by Chrome MV2 deprecation)
  - ESPN Private League Setup (Chrome), GameDayBot, v2.0 August 20 2025 — https://chromewebstore.google.com/detail/espn-private-league-setup/bjmalaafoepfooflcnhjejnopgefjgia — credibility: medium (MV3 confirmed, open-source, production use at GameDayBot.com)
  - PFF for your Fantasy League (Chrome), Pro Football Focus, v1.0 August 4 2025 — https://chromewebstore.google.com/detail/pff-for-your-fantasy-leag/enpmekoogcpafokplcfodchijhmnmbdm — credibility: high (MV3 confirmed, production SaaS with named analyst track record)
  - Flock Fantasy ESPN Quick Sync (Chrome), v1.1.1 August 2024 — https://chromewebstore.google.com/detail/flock-fantasy-espn-quick/iphbmofabopjekdpkdmpehlhoamheigo — credibility: medium (MV3, ~20k users, 2.8/5 — user reports of sync failures documented)
  - FantasyPros Support, 2024 — https://support.fantasypros.com/hc/en-us/articles/360051313453 — credibility: high (production SaaS; extension mandatory for ESPN sync)
  - Chrome MV2 Deprecation Timeline, Google, 2025 — https://developer.chrome.com/docs/extensions/develop/migrate/mv2-deprecation-timeline — credibility: high (official; Chrome 138 disables all MV2; Chrome 139 removes support entirely)
  - MDN Web Docs, "Work with the Cookies API" — https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Work_with_the_Cookies_API — credibility: high (confirms `chrome.cookies` API reads HttpOnly cookies; `document.cookie` cannot)
- **Disagreements / counterevidence:** The FantasyPros/PFF model (extension sends cookie to their server) and the GameDayBot model (extension shows cookie to user for copy-paste) represent different trust models; the latter is safer for users. The Flock Fantasy extension's low rating and reported sync failures suggest MV3 migration does not guarantee reliability.
- **Confidence:** high for the architectural pattern; medium for any specific third-party extension link remaining valid — extension status changes between seasons and requires re-verification before each NFL Draft window.
- **Implementation status:** not implemented. AutoTiers currently shows a raw form field with no guidance. This is a product/UX decision, not a `builtin_rules.py` heuristic.
- **Suggested next step:** Build a guided ESPN connect modal with: (a) numbered annotated screenshot steps specific to Chrome/Safari/Firefox, (b) inline SWID format validation, (c) a link to the GameDayBot MV3 extension as a faster path (it is open-source, copy-paste model, and confirmed MV3 — do NOT link ESPN Cookie Finder until its MV3 status is confirmed), (d) a "troubleshoot" section noting that logging out and back in refreshes both cookies if the connection fails. Re-verify all recommended extension links before the 2026 season opens.

---

### Chrome Manifest V2 Deprecation Breaks Most ESPN Cookie Extraction Extensions

- **Claim (operational form):** Chrome 138 (July 2025) disabled all Manifest V2 extensions by default with no re-enable option; Chrome 139 removes MV2 support entirely — any ESPN cookie-extraction extension still on MV2 is now non-functional on Chrome, and users on current Chrome versions cannot use it even if it appears in the Web Store.
- **Position(s) / league type(s):** Platform/infrastructure concern — applies to all ESPN private league integrations that rely on a Chrome extension for cookie extraction.
- **Reasoning:** Google's Manifest V3 migration began disabling MV2 extensions in pre-stable Chrome builds in June 2024 (Chrome 127+). By October 2024 (Chrome stable), users began seeing "this extension is no longer supported" warnings. As of Chrome 138 (July 2025), all MV2 extensions are disabled for all Chrome users and cannot be re-enabled. Chrome 139 removes the engine support entirely. The ESPN Cookie Finder extension (Hashtag Fantasy Sports) was confirmed on MV2 as of its August 25 2025 v1.2 update — despite being published after Chrome 138's release, it apparently was not migrated. This means the extension most commonly linked in third-party ESPN API docs and tutorials is now broken on Chrome for the majority of users. Three competing extensions (GameDayBot v2.0, PFF, Flock Fantasy) have migrated to MV3 and work on current Chrome. Firefox has a separate, more gradual MV3 timeline; the ESPN Cookie Finder Firefox add-on remains valid. This is a time-sensitive finding: the landscape changes before each football season as developers update (or abandon) their extensions.
- **Sources:**
  - Chrome MV2 Deprecation Timeline, Google Chrome Developers, 2025 — https://developer.chrome.com/docs/extensions/develop/migrate/mv2-deprecation-timeline — credibility: high (authoritative; states "With Chrome 138 all users...have Manifest V2 extensions disabled...Users can no longer turn them back on")
  - "Resuming the transition to Manifest V3", Chrome Developers Blog — https://developer.chrome.com/blog/resuming-the-transition-to-mv3 — credibility: high (official announcement of the rollout phases)
  - chrome-stats.com listing for ESPN Cookie Finder — confirms MV2 manifest version — credibility: medium
  - "Manifest V2 vs Manifest V3 — why 2025 was the turning point", Medium/@idmossab, 2025 — https://medium.com/@idmossab/nifest-v2-vs-manifest-v3-chrome-extensions-what-changed-and-why-2025-was-the-turning-point-53b031b70fc6 — credibility: medium (corroborating analysis of the timeline)
- **Disagreements / counterevidence:** It is possible the ESPN Cookie Finder developer updates to MV3 before or during the 2026 football season — the August 2025 v1.2 release suggests active maintenance. Verification is required each season.
- **Confidence:** high — Google's deprecation timeline is authoritative; the MV2 status of ESPN Cookie Finder is confirmed by third-party extension metadata.
- **Implementation status:** not implemented as a rule. This is an infrastructure concern for any documentation, guided flows, or help text in AutoTiers that recommends the ESPN Cookie Finder Chrome extension — those references are now potentially harmful to non-technical users who will be confused when the extension does not work.
- **Suggested next step:** Audit all AutoTiers UI copy and documentation for references to specific ESPN cookie extraction extensions. Replace any reference to "ESPN Cookie Finder" with language like "a browser extension such as ESPN Private League Setup (GameDayBot)" and include a note that extension availability should be verified at the start of each season.

---

### Bookmarklet Cannot Replace a Browser Extension for ESPN Cookie Extraction

- **Claim (operational form):** A JavaScript bookmarklet running on fantasy.espn.com cannot reliably read the espn_s2 and SWID cookies because ESPN likely marks at least some of its auth cookies as HttpOnly, which blocks `document.cookie` access; browser extensions bypass this restriction via the `chrome.cookies` API, which is the reason every production tool uses an extension rather than a bookmarklet.
- **Position(s) / league type(s):** Platform/UX concern — private ESPN leagues, all scoring formats.
- **Reasoning:** The `document.cookie` JavaScript property, which any bookmarklet would use, cannot read cookies marked with the `HttpOnly` attribute — this is a browser-enforced security boundary that prevents XSS attacks from stealing session cookies. The `chrome.cookies` API used by browser extensions operates at a higher privilege level and reads HttpOnly cookies. All production ESPN cookie extraction tools are extensions, not bookmarklets; no bookmarklet implementation exists in public repositories as of June 2026. The absence of a working public bookmarklet is itself evidence that the cookies are HttpOnly — if `document.cookie` worked, a single-line bookmarklet would be simpler and more universal than building a full extension. However: the exact `HttpOnly` status of `SWID` and `espn_s2` has not been independently confirmed from a primary source in this research session (ESPN's cookie configuration is not publicly documented). The inference is strong but not verified from inspection. MDN documents this restriction definitively; ESPN's pattern of using session cookies for auth makes HttpOnly a near-certainty for security-sensitive values.
- **Sources:**
  - MDN Web Docs, "Document: cookie property" — https://developer.mozilla.org/en-US/docs/Web/API/Document/cookie — credibility: high ("cookies with the HttpOnly attribute are inaccessible to JavaScript's Document.cookie API")
  - MDN Web Docs, "Work with the Cookies API" — https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Work_with_the_Cookies_API — credibility: high (confirms extension API reads HttpOnly cookies that page-level JS cannot)
  - Absence of any working ESPN bookmarklet in public repositories (GitHub search, developer guides) — credibility: medium (strong negative evidence; if it worked, someone would have built one)
  - cwendt94/espn-api Discussion #150, August 2025 comment by dtcarls — https://github.com/cwendt94/espn-api/discussions/150 — credibility: medium (explicitly describes extension as "easier" rather than bookmarklet, suggesting the simpler approach was never viable)
- **Disagreements / counterevidence:** It is theoretically possible that SWID (the shorter, non-sensitive-looking UUID) is not HttpOnly and could be read via `document.cookie`, while espn_s2 is. This would make a partial bookmarklet possible. However no public source confirms this split, and building a UX flow around partial extraction would be more confusing than no bookmarklet at all.
- **Confidence:** medium — the HttpOnly inference is well-supported by the architectural evidence, but the exact cookie attributes have not been directly verified by inspection in this research session.
- **Implementation status:** not implemented and should not be. This entry closes the question of whether a bookmarklet is a viable UX improvement for AutoTiers — the answer is almost certainly no.
- **Suggested next step:** Do not invest engineering time in a bookmarklet approach. The guided screenshot flow (see "Browser Extension" entry) and the optional link to the GameDayBot MV3 extension are the right lower-friction alternatives for non-technical users without AutoTiers shipping its own extension.

---

### ESPN Cookie Expiry Is Undocumented But Empirically Long-Lived

- **Claim (operational form):** The espn_s2 and SWID cookies have no publicly documented expiry period; community evidence suggests they persist for months to a full season without requiring re-extraction, but any trigger that clears browser cookies (manual clear, password change, ESPN-side session revocation) will invalidate them and require the user to re-run the extraction flow.
- **Position(s) / league type(s):** Platform/auth concern — private ESPN leagues, all scoring formats.
- **Reasoning:** The cwendt94/espn-api Discussion #150 explicitly states these cookies "remain the same through different sessions" and no community reports of routine mid-season expiry appear across the surveyed repositories. The espn_api Python library has no refresh logic — it treats the cookies as static inputs — and this design has not generated widespread bug reports about unexpected expiry. However, ESPN's technical documentation for these cookies does not exist publicly, so no SLA can be stated. Known invalidation triggers: (1) user manually clears ESPN cookies in their browser; (2) user changes ESPN password (sessions are typically revoked server-side); (3) ESPN performs a forced re-auth (rare, but documented in the cwendt94 issue tracker historically around major site redesigns). The practical implication for AutoTiers: stored credentials may silently expire between seasons; the connect flow should always include a "re-authenticate" path that is easy to find.
- **Sources:**
  - cwendt94/espn-api Discussion #150, 2020–2025 — https://github.com/cwendt94/espn-api/discussions/150 — credibility: medium (empirical community evidence; "remains the same through different sessions")
  - cwendt94/espn-api requests/espn_requests.py — https://github.com/cwendt94/espn-api/blob/master/espn_api/requests/espn_requests.py — credibility: medium (no refresh logic present; confirms static-cookie design has not generated widespread complaints)
  - Absence of ESPN official cookie documentation — credibility: low-medium (negative evidence; if expiry were short, user complaints would be common)
- **Disagreements / counterevidence:** mkreiser/ESPN-Fantasy-Football-API issue #133 reported that espn_s2 could not be found at all — this was unresolved and may reflect a scenario where a user's ESPN session was in an unusual state, not a systemic cookie removal. No widespread corroboration of espn_s2 disappearing was found.
- **Confidence:** medium — strong empirical signal that cookies are long-lived, but the absence of official documentation means any ESPN backend change could invalidate this assumption without notice.
- **Implementation status:** not implemented as a rule. The implication for `backend/app/integrations/espn.py` is that the current error handling for `EspnAuthRequired` should surface a user-friendly "your ESPN session may have expired — please re-authenticate" message rather than a generic API error.
- **Suggested next step:** Ensure the `EspnAuthRequired` exception path in the API surfaces a clear re-authentication prompt to the user with a direct link back to the ESPN connect modal, and consider adding a periodic health-check ping at season start that detects expired credentials before the user tries to generate tiers.

---

### ESPN "Make League Public" Is a Zero-Auth Alternative for Cooperative League Managers

- **Claim (operational form):** An ESPN league manager can toggle "Make League Viewable to Public: Yes" in league settings, after which the league's scoring settings and draft data become accessible via the ESPN API without any cookie authentication — eliminating the SWID/espn_s2 requirement entirely.
- **Position(s) / league type(s):** Platform/auth concern — ESPN private leagues where the AutoTiers user is also the league manager or can ask the LM.
- **Reasoning:** ESPN officially documents the "Make League Viewable to Public" setting. Public leagues are accessible by anyone via the API without credentials. AutoTiers already handles public leagues (the `fetch_league` function passes cookies only when present; if absent it falls through to the unauthenticated request). The catch: this is a league-level setting that requires LM action, it exposes all league data to the public internet, and not every user is their own LM. It is a valid escape hatch to surface to users — "if your league manager is comfortable making the league public, you can skip the cookie step."
- **Sources:**
  - ESPN Fan Support, "Making a Private League Viewable to the Public" — https://support.espn.com/hc/en-us/articles/360000064451-Making-a-Private-League-Viewable-to-the-Public — credibility: high (official ESPN documentation)
  - Multiple developer guides (stmorse, dustysturner) independently describe this as "the easiest workaround" — credibility: medium
- **Disagreements / counterevidence:** Some leagues have privacy reasons for staying private (competitive meta, trade history). Surfacing this option should be framed as optional, not the primary path.
- **Confidence:** high — this is an official ESPN feature, not reverse-engineered behavior.
- **Implementation status:** not implemented as a UX prompt. AutoTiers handles public leagues correctly in `backend/app/integrations/espn.py` (cookies passed only when present). The gap is that the connect flow does not tell users this option exists.
- **Suggested next step:** In the ESPN connect modal, below the cookie-paste form, add a collapsed "Alternative: Public League" section explaining the LM toggle. Link to the ESPN support article. No backend changes required.

---

## Entry template

```
### <Short heuristic name>

- **Claim (operational form):** <one sentence the mathematician could turn into a formula>
- **Position(s) / league type(s):** <where this applies — e.g. "RB, standard + half-PPR redraft">
- **Reasoning:** <one paragraph: why is this thought to be true? what's the mechanism?>
- **Sources:**
  - <Author, Year, Title — URL — credibility (high/medium/low)>
  - ...
- **Disagreements / counterevidence:** <if any source disagrees, name them and what they say>
- **Confidence:** <high | medium | low> — <one sentence on why>
- **Implementation status:** <not implemented | implemented as <file:function> | superseded by <other entry>>
- **Suggested next step:** <if not implemented and worth shipping, one sentence on what the rule would compute>
```

## Credibility rubric

- **High:** Established analyst publications with public track records (PFF, FantasyPoints, Establish The Run, RotoViz, Football Outsiders, PFR), academic sports-analytics papers.
- **Medium:** Podcasts with named analysts, well-cited Substacks/X threads from credentialed people, longform with shown reasoning.
- **Low:** Reddit consensus, unsourced rules of thumb, generic ranking sites without methodology. Useful as folk-knowledge signal, never as the only source.

A heuristic with three medium-credibility sources that converge is stronger than one high-credibility source making a contrarian claim. Surface the convergence/divergence explicitly in the entry's "Confidence" line.
