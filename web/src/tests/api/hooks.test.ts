import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { downloadDraftXlsx, downloadDebugCsv } from "@/api/hooks";
import type { TieredPlayer } from "@/api/types";

const basePlayer: TieredPlayer = {
  overall_rank: 1,
  player_id: "001",
  name: "Test Player",
  position: "WR",
  team: "KC",
  age: 25,
  overall_tier: 1,
  positional_tier: "WR1",
  adjusted_score: 300.0,
  projected_score_raw: 290.0,
  prior_year_actual: null,
  espn_projection: null,
  fantasypros_projection: null,
  avg_projection: null,
  adp_standard: null,
  adp_ppr: null,
  adp_dynasty: null,
  league_adp: null,
  vbd_score: 150.0,
  position_replacement: 150.0,
  flags: [],
  rules_applied: [],
  rule_applications: [],
  is_favorite_player: null,
  is_favorite_team: null,
};

describe("file downloads", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let appendChild: ReturnType<typeof vi.fn>;
  let removeChild: ReturnType<typeof vi.fn>;
  let click: ReturnType<typeof vi.fn>;
  let anchor: { href: string; download: string; click: ReturnType<typeof vi.fn> };
  const originalCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    revokeObjectURL = vi.fn();
    appendChild = vi.fn();
    removeChild = vi.fn();
    click = vi.fn();
    anchor = { href: "", download: "", click };

    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });

    vi.spyOn(document.body, "appendChild").mockImplementation(appendChild);
    vi.spyOn(document.body, "removeChild").mockImplementation(removeChild);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        return anchor as unknown as HTMLAnchorElement;
      }
      return originalCreateElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("downloadDraftXlsx", () => {
    it("builds a non-empty xlsx Blob, links, and clicks it", async () => {
      await downloadDraftXlsx([basePlayer], "standard");

      expect(createObjectURL).toHaveBeenCalledOnce();
      const blobArg = createObjectURL.mock.calls[0][0] as Blob;
      expect(blobArg).toBeInstanceOf(Blob);
      expect(blobArg.size).toBeGreaterThan(0);
      expect(click).toHaveBeenCalledOnce();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
    });

    it("falls back to tiers.xlsx when no profile name is given", async () => {
      await downloadDraftXlsx([basePlayer], "standard");
      expect(anchor.download).toBe("tiers.xlsx");
    });

    it("derives the filename from the profile name, scoring format, and date", async () => {
      await downloadDraftXlsx([basePlayer], "half_ppr", "My League #1");
      // e.g. "my-league-1-half-ppr-tiers-2026-07-12.xlsx" — date is the real
      // current date, so assert the shape rather than a frozen day.
      expect(anchor.download).toMatch(
        /^my-league-1-half-ppr-tiers-\d{4}-\d{2}-\d{2}\.xlsx$/,
      );
    });

    it("falls back to tiers.xlsx when the profile name slugifies to nothing", async () => {
      await downloadDraftXlsx([basePlayer], "standard", "!!!");
      expect(anchor.download).toBe("tiers.xlsx");
    });

    it("does not make a network request", async () => {
      const fetchSpy = vi.spyOn(global, "fetch");
      await downloadDraftXlsx([basePlayer], "ppr");
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("accepts tier label overrides without throwing", async () => {
      await expect(
        downloadDraftXlsx([basePlayer], "standard", "My League", { 1: "Studs" }),
      ).resolves.toBeUndefined();
      expect(click).toHaveBeenCalledOnce();
    });

    // Sincerity guard for the lazy-load (bug-class #7). The xlsx builder + the
    // ~20 kB write-excel-file library must be pulled in via a dynamic import()
    // INSIDE downloadDraftXlsx so Rollup code-splits them out of the main chunk.
    // This reads hooks.ts source directly and FAILS the moment someone reverts to
    // a top-level `import { buildDraftXlsxBlob } from "@/lib/xlsx"`. A behavioural
    // test can't distinguish static from dynamic here (both produce the same
    // Blob), so the boundary is asserted structurally — which is the property the
    // build relies on.
    it("imports @/lib/xlsx dynamically, not statically (code-split boundary)", async () => {
      const fs = await import("node:fs/promises");
      const url = await import("node:url");
      const path = await import("node:path");
      const here = path.dirname(url.fileURLToPath(import.meta.url));
      const hooksPath = path.resolve(here, "../../api/hooks.ts");
      const src = await fs.readFile(hooksPath, "utf-8");

      // No top-level VALUE import of the xlsx builder (a `import type` is fine).
      expect(src).not.toMatch(/^\s*import\s+\{[^}]*buildDraftXlsxBlob[^}]*\}\s+from\s+["']@\/lib\/xlsx["']/m);
      // The builder is loaded via a dynamic import() of @/lib/xlsx.
      expect(src).toMatch(/await\s+import\(\s*["']@\/lib\/xlsx["']\s*\)/);
    });
  });

  describe("downloadDebugCsv", () => {
    it("creates a download link and clicks it", () => {
      downloadDebugCsv([basePlayer]);

      expect(createObjectURL).toHaveBeenCalledOnce();
      expect(click).toHaveBeenCalledOnce();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
    });

    it("downloads as tiers-debug.csv", () => {
      downloadDebugCsv([basePlayer]);
      expect(anchor.download).toBe("tiers-debug.csv");
    });

    it("accepts tier label overrides without throwing", () => {
      expect(() => downloadDebugCsv([basePlayer], { 1: "Studs" })).not.toThrow();
      expect(click).toHaveBeenCalledOnce();
    });
  });
});
