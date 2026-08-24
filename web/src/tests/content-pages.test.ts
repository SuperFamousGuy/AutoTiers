import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// The AdSense-review content library (issue #1250) is a set of static HTML pages
// under web/public/, served verbatim rather than bundled through the app, so —
// like terms-html.test.ts — we assert against the files on disk. These checks
// lock in that every page is present, self-consistent (title, description,
// canonical, shared stylesheet, internal linking) and enrolled in the sitemap,
// so a client-only regression can't quietly turn them back into the empty SPA
// shell the reviewer was shown before.

const publicDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../public",
);

function read(name: string): string {
  return readFileSync(path.join(publicDir, name), "utf8");
}

// The eight per-theme rule guides plus the hub, glossary and FAQ. methodology.html
// is delivered by PR #1249 and is intentionally not asserted here.
const RULE_GUIDES = [
  "rules-workload.html",
  "rules-opportunity.html",
  "rules-regression.html",
  "rules-aging.html",
  "rules-rookies.html",
  "rules-situation.html",
  "rules-kickers.html",
  "rules-data.html",
];
const CONTENT_PAGES = ["content.html", "glossary.html", "faq.html", ...RULE_GUIDES];

describe("content library pages (#1250)", () => {
  it("ships at least 8 substantial pages beyond methodology.html", () => {
    // Acceptance criterion: 8–10 substantial pages. 11 here (3 + 8 guides).
    expect(CONTENT_PAGES.length).toBeGreaterThanOrEqual(8);
  });

  it.each(CONTENT_PAGES)("%s is a complete, self-consistent HTML document", (page) => {
    const html = read(page);
    expect(html).toMatch(/^<!DOCTYPE html>/i);
    // A real, descriptive title — not the app's generic shell title.
    expect(html).toMatch(/<title>[^<]*AutoTiers<\/title>/);
    // A meta description for the reviewer / crawler.
    expect(html).toMatch(/<meta name="description" content="[^"]{40,}"/);
    // Canonical URL pointing at this exact page.
    expect(html).toContain(`<link rel="canonical" href="https://auto-tiers.com/${page}"`);
    // Uses the shared content stylesheet (prerendered, not client-rendered).
    expect(html).toContain('<link rel="stylesheet" href="/content.css" />');
    // Substantial prose, not a stub.
    expect(html.length).toBeGreaterThan(2500);
  });

  it.each(CONTENT_PAGES)("%s links back into the app and the site", (page) => {
    const html = read(page);
    // Every page links to the live app...
    expect(html).toContain('href="https://auto-tiers.com"');
    // ...and the child pages cross-link back to the guides hub (the hub itself
    // instead links out to the children).
    if (page === "content.html") {
      expect(html).toContain('href="/glossary.html"');
      expect(html).toContain('href="/faq.html"');
      for (const guide of RULE_GUIDES) {
        expect(html).toContain(`href="/${guide}"`);
      }
    } else {
      expect(html).toContain('href="/content.html"');
    }
  });

  it("the shared stylesheet exists", () => {
    expect(read("content.css").length).toBeGreaterThan(500);
  });
});

describe("sitemap.xml (#1250)", () => {
  const sitemap = read("sitemap.xml");

  it("is a well-formed urlset", () => {
    expect(sitemap).toMatch(/^<\?xml version="1\.0" encoding="UTF-8"\?>/);
    expect(sitemap).toContain("<urlset");
    expect(sitemap).toContain("</urlset>");
  });

  it("enrolls every content page", () => {
    for (const page of CONTENT_PAGES) {
      expect(sitemap).toContain(`<loc>https://auto-tiers.com/${page}</loc>`);
    }
  });

  it("includes the methodology page and the app root", () => {
    expect(sitemap).toContain("<loc>https://auto-tiers.com/</loc>");
    expect(sitemap).toContain("<loc>https://auto-tiers.com/methodology.html</loc>");
  });
});
