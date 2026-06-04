import { cn } from "@/lib/utils";

interface LogoProps {
  /** Extra classes for the wrapper (e.g. sizing or layout overrides). */
  className?: string;
  /** Render the "AutoTiers" wordmark next to the mark. Defaults to true. */
  showWordmark?: boolean;
}

/**
 * AutoTiers brand logo: a "tier ladder" mark (three ascending bars) plus the
 * "AutoTiers" wordmark. The mark inherits its color from `currentColor`, so the
 * brand accent is driven via Tailwind `text-primary` (amber in dark mode,
 * primary in light mode) and stays consistent with other primary-colored UI.
 *
 * The mark is decorative (`aria-hidden`); the visible wordmark carries the
 * accessible name. When `showWordmark` is false, callers must supply their own
 * accessible label (e.g. an `aria-label` on a wrapping link).
 */
export function Logo({ className, showWordmark = true }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 24 24"
        className="h-full w-auto text-primary"
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <rect x="3" y="13" width="4" height="8" rx="1" />
        <rect x="10" y="8" width="4" height="13" rx="1" />
        <rect x="17" y="3" width="4" height="18" rx="1" />
      </svg>
      {showWordmark && (
        <span className="font-bold tracking-tight text-foreground">AutoTiers</span>
      )}
    </span>
  );
}
