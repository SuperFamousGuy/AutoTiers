import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  adsDismissed,
  adsEnabled,
  adsenseClientId,
  dismissAds,
  loadAdSenseScript,
} from "@/lib/ads";

const SCRIPT_SELECTOR = "script[data-autotiers-adsense]";

afterEach(() => {
  vi.unstubAllEnvs();
  sessionStorage.clear();
  document.head.querySelectorAll(SCRIPT_SELECTOR).forEach((el) => el.remove());
});

describe("adsEnabled", () => {
  it("is false by default (opt-in monetization)", () => {
    expect(adsEnabled()).toBe(false);
  });

  it("is true only for the exact string \"true\"", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    expect(adsEnabled()).toBe(true);
  });

  it("is false for other truthy-looking values", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "1");
    expect(adsEnabled()).toBe(false);
  });
});

describe("adsenseClientId", () => {
  it("defaults to an empty string when unset", () => {
    expect(adsenseClientId()).toBe("");
  });

  it("returns the configured publisher id", () => {
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    expect(adsenseClientId()).toBe("ca-pub-123");
  });
});

describe("session dismissal", () => {
  it("starts not dismissed", () => {
    expect(adsDismissed()).toBe(false);
  });

  it("persists a dismissal for the session", () => {
    dismissAds();
    expect(adsDismissed()).toBe(true);
  });
});

describe("loadAdSenseScript", () => {
  it("does nothing when ads are disabled", () => {
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    loadAdSenseScript();
    expect(document.querySelector(SCRIPT_SELECTOR)).toBeNull();
  });

  it("does nothing when no client id is configured", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    loadAdSenseScript();
    expect(document.querySelector(SCRIPT_SELECTOR)).toBeNull();
  });

  it("injects the loader script once when enabled and configured", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");

    loadAdSenseScript();
    loadAdSenseScript(); // idempotent — second call must not duplicate

    const scripts = document.querySelectorAll(SCRIPT_SELECTOR);
    expect(scripts).toHaveLength(1);
    const src = scripts[0].getAttribute("src") ?? "";
    expect(src).toContain("adsbygoogle.js");
    expect(src).toContain("client=ca-pub-123");
  });
});
