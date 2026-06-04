import { describe, it, expect } from "vitest";
import { playerHeadshotUrl, teamLogoUrl } from "@/lib/espn-cdn";

describe("espn-cdn", () => {
  describe("playerHeadshotUrl", () => {
    it("returns the correct ESPN headshot URL for a given espn id", () => {
      expect(playerHeadshotUrl("3918298")).toBe(
        "https://a.espncdn.com/i/headshots/nfl/players/full/3918298.png"
      );
    });
  });

  describe("teamLogoUrl", () => {
    it("lowercases the team code for KC", () => {
      expect(teamLogoUrl("KC")).toBe(
        "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png"
      );
    });

    it("lowercases the team code for NE", () => {
      expect(teamLogoUrl("NE")).toBe(
        "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png"
      );
    });

    it("lowercases the team code for BUF", () => {
      expect(teamLogoUrl("BUF")).toBe(
        "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png"
      );
    });
  });
});
