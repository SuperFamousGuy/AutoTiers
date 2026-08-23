import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// terms.html is a static asset under web/public/, not bundled through the app,
// so we assert against the file on disk. These checks lock in the advertising
// acknowledgment added for issue #392.
const termsPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../public/terms.html",
);
const html = readFileSync(termsPath, "utf8");

describe("terms.html advertising acknowledgment", () => {
  it("notes that AutoTiers displays third-party advertising", () => {
    expect(html).toMatch(/third-party advertising/i);
  });

  it("states the vendors' own terms/policies govern that advertising", () => {
    expect(html).toMatch(/vendors' own terms and policies/i);
  });

  it("points to the privacy policy for advertising data handling", () => {
    expect(html).toContain('href="/privacy.html"');
  });

  it("has a dedicated Advertising heading matching sibling h2 levels", () => {
    expect(html).toContain("<h2>Advertising</h2>");
  });

  it("bumps the effective date since the copy changed", () => {
    expect(html).toContain("Effective date: August 23, 2026");
  });
});

// Issue #1252: the v1 account system (Yahoo/Google OAuth, ESPN session cookies,
// Sleeper usernames, league linking, per-user accounts) was torn down in PR #850.
// These checks lock in that the Terms no longer describe accounts/authentication
// that the login-free app does not have.
describe("terms.html has no stale account/OAuth claims", () => {
  it("does not describe signing in or connecting fantasy accounts", () => {
    expect(html).not.toMatch(/OAuth/i);
    expect(html).not.toMatch(/lets you sign in and connect/i);
    expect(html).not.toMatch(/connect fantasy accounts/i);
    expect(html).not.toMatch(/\bSWID\b|espn_s2/i);
  });

  it("does not tell users to delete an account from within the Service", () => {
    expect(html).not.toMatch(/delete your account/i);
  });

  it("states that no account is required", () => {
    expect(html).toContain("<h2>No Account Required</h2>");
    expect(html).toMatch(/does not require you to create an account/i);
  });
});
