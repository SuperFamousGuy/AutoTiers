import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { useId } from "react";

interface GenerateButtonProps {
  disabled: boolean;
  isPending: boolean;
  onClick: () => void;
  /**
   * Why Generate is disabled, or null when it's enabled. Surfaced as a native
   * `title` (desktop hover) and via `aria-describedby` to an sr-only span so
   * keyboard/screen-reader users learn the same specific precondition (#838).
   */
  disabledReason?: string | null;
}

export function GenerateButton({ disabled, isPending, onClick, disabledReason }: GenerateButtonProps) {
  const reasonId = useId();
  // Only surface the reason for the precondition-disabled state, not while a
  // generate is in flight — the pending live region below owns that message.
  const showReason = disabled && !isPending && !!disabledReason;

  return (
    <>
      <Button
        data-tour="generate"
        // Block the click ourselves when disabled/pending: the precondition
        // path below uses aria-disabled (not native `disabled`), so the browser
        // no longer suppresses it for us.
        onClick={disabled || isPending ? undefined : onClick}
        // Precondition-disabled uses aria-disabled rather than the native
        // `disabled` attribute so the button stays focusable and hoverable — a
        // natively disabled button gets `disabled:pointer-events-none` (no hover,
        // so the `title` tooltip never shows) and leaves the tab order (screen
        // readers never reach it to announce `aria-describedby`) (#838). Pending
        // keeps native `disabled`: there's no reason to surface then, and it's
        // the plainer guard for an in-flight request.
        disabled={isPending}
        aria-disabled={disabled || isPending}
        aria-busy={isPending}
        title={showReason ? disabledReason : undefined}
        aria-describedby={showReason ? reasonId : undefined}
        size="default"
        // WCAG AA text contrast (#1054). White on amber-500 was ~2.2:1; amber-700
        // clears 4.5:1 (≈5.0), amber-800 on hover clears it further. The disabled
        // states can't rely on a big opacity dim: blending white text + amber toward
        // the page background collapses contrast below 4.5:1 at any amber shade, so
        // instead of `opacity-70` we darken to amber-900 (white ≈9:1 solid) and dim
        // only to opacity-90 — that keeps ≥4.5:1 in light mode (dark mode only raises
        // it, since the blend goes darker) across the aria-disabled (precondition) and
        // native disabled (pending) states. cn()/twMerge lets these override the
        // Button base's `disabled:opacity-50`.
        className="bg-amber-700 hover:bg-amber-800 text-white border-0 disabled:bg-amber-900 disabled:opacity-90 aria-disabled:bg-amber-900 aria-disabled:opacity-90 aria-disabled:cursor-not-allowed lg:h-11 lg:px-8 lg:text-base"
      >
        {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        Generate
      </Button>
      {showReason && (
        <span id={reasonId} className="sr-only">
          {disabledReason}
        </span>
      )}
      <span role="status" aria-live="polite" className="sr-only">
        {isPending ? "Generating tier list…" : null}
      </span>
    </>
  );
}
