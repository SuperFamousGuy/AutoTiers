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
        className="bg-amber-500 hover:bg-amber-600 text-white border-0 disabled:opacity-70 aria-disabled:opacity-70 aria-disabled:cursor-not-allowed lg:h-11 lg:px-8 lg:text-base"
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
