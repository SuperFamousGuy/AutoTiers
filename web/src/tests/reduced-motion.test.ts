import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// index.css is processed by Tailwind at build time, and jsdom does not evaluate
// stylesheets or media queries, so we assert against the source on disk. These
// checks lock in the prefers-reduced-motion baseline added for issue #810:
// spinners, skeleton pulses, and dialog/toast transitions must stop animating
// when the user has asked their OS/browser to reduce motion.
const cssPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../index.css",
);
const css = readFileSync(cssPath, "utf8");

// Extract the body of the `@media (prefers-reduced-motion: reduce)` block so the
// assertions below apply specifically to that rule, not to any incidental match
// elsewhere in the file.
function reducedMotionBlock(source: string): string {
  const start = source.search(/@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)/);
  if (start === -1) return "";
  // Walk braces from the media query's opening `{` to its matching close.
  const open = source.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}") {
      depth--;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  return "";
}

describe("index.css prefers-reduced-motion baseline", () => {
  const block = reducedMotionBlock(css);

  it("defines a prefers-reduced-motion: reduce media query", () => {
    expect(block).not.toBe("");
  });

  it("targets all elements including pseudo-elements", () => {
    expect(block).toMatch(/\*\s*,/);
    expect(block).toMatch(/\*::before/);
    expect(block).toMatch(/\*::after/);
  });

  it("collapses animation duration so spinners and pulses stop animating", () => {
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
  });

  it("caps animation iteration count so looping animations do not repeat", () => {
    expect(block).toMatch(/animation-iteration-count:\s*1\s*!important/);
  });

  it("collapses transition duration so dialog/toast transitions do not animate", () => {
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
  });
});
