import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { downloadCsv } from "@/api/hooks";
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

describe("downloadCsv", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let appendChild: ReturnType<typeof vi.fn>;
  let removeChild: ReturnType<typeof vi.fn>;
  let click: ReturnType<typeof vi.fn>;
  const originalCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    revokeObjectURL = vi.fn();
    appendChild = vi.fn();
    removeChild = vi.fn();
    click = vi.fn();

    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });

    vi.spyOn(document.body, "appendChild").mockImplementation(appendChild);
    vi.spyOn(document.body, "removeChild").mockImplementation(removeChild);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        return { href: "", download: "", click } as unknown as HTMLAnchorElement;
      }
      return originalCreateElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a download link and clicks it", () => {
    downloadCsv([basePlayer]);

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });

  it("does not make a network request", () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    downloadCsv([basePlayer]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("accepts tier label overrides without throwing", () => {
    expect(() => downloadCsv([basePlayer], { 1: "Studs" })).not.toThrow();
    expect(click).toHaveBeenCalledOnce();
  });
});
