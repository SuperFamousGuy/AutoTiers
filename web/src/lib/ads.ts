/**
 * Ad configuration + Google AdSense loader.
 *
 * Monetization is OFF by default. Ads render only when a deployment opts in via
 * VITE_ADS_ENABLED="true". When a Google AdSense publisher id is supplied through
 * VITE_ADSENSE_CLIENT_ID, real AdSense units fill the slots; otherwise AdSlot
 * shows a subtle in-house placeholder so the layout is previewable without any
 * network call (and so tests/dev never reach out to Google).
 *
 * Every helper reads import.meta.env at call time rather than at module load, so
 * tests can flip the flags with vi.stubEnv() without re-importing this module.
 */

/** True when the deployment has opted into showing ads. */
export function adsEnabled(): boolean {
  return import.meta.env.VITE_ADS_ENABLED === "true";
}

/** The Google AdSense publisher id (e.g. "ca-pub-…"), or "" when unconfigured. */
export function adsenseClientId(): string {
  return import.meta.env.VITE_ADSENSE_CLIENT_ID ?? "";
}

// Session-scoped so a dismissal lasts the visit but ads return next session.
const SESSION_KEY = "ads_dismissed";

/** Whether the user has hidden ads for this browser session. */
export function adsDismissed(): boolean {
  try {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    // sessionStorage unavailable (private mode / SSR) — treat as not dismissed.
    return false;
  }
}

/** Hide ads for the remainder of this browser session. */
export function dismissAds(): void {
  try {
    sessionStorage.setItem(SESSION_KEY, "1");
  } catch {
    // sessionStorage unavailable — ignore; ads simply won't persist a dismissal.
  }
}

/** Marker attribute so the loader is idempotent across many AdSlot mounts. */
const SCRIPT_MARKER = "data-autotiers-adsense";

/**
 * Inject the AdSense loader script exactly once. No-op when ads are disabled, no
 * client id is configured, the script is already present, or there's no DOM.
 *
 * The "already present" check matches ANY adsbygoogle.js tag, not just one we
 * injected: index.html ships a static loader for AdSense site verification, and
 * matching only our own marker meant every production page loaded Google's tag
 * twice. adsbygoogle.js is not designed to be evaluated twice on one page.
 */
export function loadAdSenseScript(): void {
  if (!adsEnabled()) return;
  const client = adsenseClientId();
  if (!client) return;
  if (typeof document === "undefined") return;
  if (document.querySelector('script[src*="adsbygoogle.js"]')) return;

  const script = document.createElement("script");
  script.src =
    "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" +
    encodeURIComponent(client);
  script.async = true;
  script.crossOrigin = "anonymous";
  script.setAttribute(SCRIPT_MARKER, "1");
  document.head.appendChild(script);
}
