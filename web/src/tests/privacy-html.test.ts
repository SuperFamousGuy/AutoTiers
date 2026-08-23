import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// privacy.html is a static asset under web/public/, not bundled through the app,
// so we assert against the file on disk. These checks lock in the rewrite from
// issue #1252: the v1 account system (Yahoo/Google OAuth, email collection, ESPN
// session cookies, Sleeper usernames, league linking, SES transactional email)
// was torn down in PR #850, and the policy must describe the login-free,
// localStorage-based app that exists today.
const privacyPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../public/privacy.html",
);
const html = readFileSync(privacyPath, "utf8");

describe("privacy.html has no stale account/OAuth claims", () => {
  it("makes no claim about collecting OAuth credentials", () => {
    // "no OAuth" (stating absence) is fine; collecting OAuth tokens is the drift.
    expect(html).not.toMatch(/OAuth tokens/i);
    expect(html).not.toMatch(/from Yahoo or Google OAuth/i);
  });

  it("does not claim to collect an email address", () => {
    // The only email in the doc is the mailto: support contact, not collection.
    expect(html).not.toMatch(/your email address/i);
    expect(html).not.toMatch(/email address \(from/i);
  });

  it("does not describe ESPN session cookies or Sleeper usernames", () => {
    expect(html).not.toMatch(/\bSWID\b/);
    expect(html).not.toMatch(/espn_s2/);
    expect(html).not.toMatch(/Sleeper username/i);
  });

  it("does not describe league linking or per-user accounts", () => {
    expect(html).not.toMatch(/league linking|link(?:ed|ing) your league/i);
    expect(html).not.toMatch(/maintain your AutoTiers account/i);
    expect(html).not.toMatch(/deleting your autotiers account/i);
  });

  it("does not describe SES transactional email or password resets", () => {
    expect(html).not.toMatch(/\bSES\b/);
    expect(html).not.toMatch(/password reset/i);
  });
});

describe("privacy.html describes the app as it is today", () => {
  it("states there is no account / login / OAuth", () => {
    expect(html).toMatch(/without creating an account/i);
    expect(html).toMatch(/no sign-up, no login, and no OAuth/i);
  });

  it("describes localStorage-based settings and favorites", () => {
    expect(html).toMatch(/localStorage/);
    expect(html).toMatch(/stays in your browser and is not transmitted/i);
  });

  it("describes anonymous feedback with no identity attached", () => {
    expect(html).toMatch(/Feedback is anonymous/i);
  });
});

describe("privacy.html advertising section stays accurate for AdSense", () => {
  it("still names Google AdSense", () => {
    expect(html).toMatch(/Google AdSense/);
  });

  it("keeps a dedicated Advertising & Cookies heading", () => {
    expect(html).toContain("<h2>Advertising &amp; Cookies</h2>");
  });

  it("still links Google's partner-sites and ad-settings pages", () => {
    expect(html).toContain(
      'href="https://policies.google.com/technologies/partner-sites"',
    );
    expect(html).toContain('href="https://www.google.com/settings/ads"');
  });
});

describe("privacy.html effective date", () => {
  it("was updated when the copy changed", () => {
    expect(html).toContain("Effective date: August 23, 2026");
  });
});
