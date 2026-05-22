import { describe, it, expect } from "vitest";
import { relativeTime, freshnessLevel } from "@/lib/format";

describe("relativeTime", () => {
  const now = new Date("2026-05-21T12:00:00Z");

  it("returns 'just now' for under 1 minute", () => {
    expect(relativeTime("2026-05-21T11:59:30Z", now)).toBe("just now");
  });

  it("returns minutes for under 1 hour", () => {
    expect(relativeTime("2026-05-21T11:30:00Z", now)).toBe("30 minutes ago");
  });

  it("returns hours for under 1 day", () => {
    expect(relativeTime("2026-05-21T09:00:00Z", now)).toBe("3 hours ago");
  });

  it("returns days for under 1 week", () => {
    expect(relativeTime("2026-05-19T12:00:00Z", now)).toBe("2 days ago");
  });

  it("returns weeks for older", () => {
    expect(relativeTime("2026-05-01T12:00:00Z", now)).toBe("2 weeks ago");
  });

  it("returns 'unknown' for null", () => {
    expect(relativeTime(null, now)).toBe("unknown");
  });
});

describe("freshnessLevel", () => {
  const now = new Date("2026-05-21T12:00:00Z");

  it("returns 'fresh' for under 3 days", () => {
    expect(freshnessLevel("2026-05-20T12:00:00Z", now)).toBe("fresh");
  });

  it("returns 'stale' for 3-7 days", () => {
    expect(freshnessLevel("2026-05-17T12:00:00Z", now)).toBe("stale");
  });

  it("returns 'old' for >7 days", () => {
    expect(freshnessLevel("2026-05-10T12:00:00Z", now)).toBe("old");
  });

  it("returns 'unknown' for null", () => {
    expect(freshnessLevel(null, now)).toBe("unknown");
  });
});
