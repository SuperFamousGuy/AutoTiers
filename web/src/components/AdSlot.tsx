/**
 * AdSlot — a small, clearly-labelled, env-gated advertisement unit.
 *
 * Renders nothing unless ads are enabled (VITE_ADS_ENABLED="true") and the user
 * hasn't dismissed ads this session. When a Google AdSense client id + slot id
 * are configured it renders a real <ins class="adsbygoogle"> unit and asks
 * AdSense to fill it; otherwise it shows a subtle in-house placeholder so the
 * slot stays previewable in dev and never makes a network call in tests.
 *
 * Tasteful by design: a slim, muted strip with an explicit "Advertisement"
 * label, dark-mode aware, and dismissible for the session.
 */
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  adsDismissed,
  adsEnabled,
  adsenseClientId,
  dismissAds,
  loadAdSenseScript,
} from "@/lib/ads";

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

interface AdSlotProps {
  /** AdSense ad-unit slot id (data-ad-slot). Real ads only fill when present. */
  slot?: string;
  /** Whether the user can hide the ad for the session. Default true. */
  dismissible?: boolean;
  className?: string;
}

export function AdSlot({ slot, dismissible = true, className }: AdSlotProps) {
  const [dismissed, setDismissed] = useState(() => adsDismissed());
  // Guards the AdSense push so a re-render never double-fills the same slot.
  const pushed = useRef(false);

  const enabled = adsEnabled();
  const client = adsenseClientId();
  const showReal = enabled && Boolean(client) && Boolean(slot);

  useEffect(() => {
    if (!showReal || dismissed || pushed.current) return;
    loadAdSenseScript();
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
      pushed.current = true;
    } catch {
      // AdSense not ready or blocked by the client — leave the unit empty
      // rather than surfacing an error to the user.
    }
  }, [showReal, dismissed]);

  if (!enabled || dismissed) return null;

  return (
    <aside
      aria-label="Advertisement"
      className={cn(
        "relative flex flex-col items-center justify-center gap-0.5 border-t border-border bg-muted/30 px-4 py-2 text-center",
        className,
      )}
    >
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
        Advertisement
      </span>
      {showReal ? (
        <ins
          className="adsbygoogle block w-full"
          style={{ display: "block", minHeight: 50 }}
          data-ad-client={client}
          data-ad-slot={slot}
          data-ad-format="horizontal"
          data-full-width-responsive="true"
        />
      ) : (
        <span
          className="flex w-full items-center justify-center text-xs text-muted-foreground"
          style={{ minHeight: 50 }}
        >
          Your ad could be here — AutoTiers stays free thanks to sponsors.
        </span>
      )}
      {dismissible && (
        <button
          type="button"
          aria-label="Dismiss advertisement"
          onClick={() => {
            dismissAds();
            setDismissed(true);
          }}
          className="absolute right-1.5 top-1.5 rounded-sm opacity-60 hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </aside>
  );
}
