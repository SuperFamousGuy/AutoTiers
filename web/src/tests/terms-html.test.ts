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
    expect(html).toContain("Effective date: June 21, 2026");
  });
});
