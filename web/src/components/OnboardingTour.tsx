import { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ONBOARDING_STEPS } from "@/lib/onboardingSteps";

interface OnboardingTourProps {
  stepIndex: number;
  totalSteps: number;
  onNext: () => void;
  onBack: () => void;
  onGoTo: (i: number) => void;
  onSkip: () => void;
  /** Called on step entry so the parent can switch the active mobile panel. */
  onStepPanel?: (panel: "settings" | "rules" | "tiers") => void;
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PAD = 8; // highlight padding around the anchored element
const POPOVER_GAP = 12; // gap between highlight and popover

/**
 * Interactive onboarding walkthrough. Highlights the real UI element for the
 * current step (dimmed backdrop + ring) and shows a popover explaining what to
 * do and why. Advances via Next/Back, the progress dots, or Finish on the last
 * step. Skips via the X button or Escape.
 *
 * Accessibility:
 *  - role="dialog" + aria-modal so screen readers treat it as a focused task.
 *  - Focus moves into the popover on mount; Tab is trapped within it; Escape skips.
 *  - The highlighted target is described to the user in plain copy, not by colour
 *    alone (the step body names the panel/button).
 *  - Backdrop click is intentionally a no-op (a tour shouldn't dismiss on a stray
 *    click); only X / Skip / Escape end the tour.
 */
export function OnboardingTour({
  stepIndex,
  totalSteps,
  onNext,
  onBack,
  onGoTo,
  onSkip,
  onStepPanel,
}: OnboardingTourProps) {
  const step = ONBOARDING_STEPS[stepIndex];
  const popoverRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  const isFirst = stepIndex === 0;
  const isLast = stepIndex === totalSteps - 1;

  // On entering a step, switch the mobile panel so the anchor is on screen.
  // useLayoutEffect (not useEffect) so the panel switch commits before the
  // measure pass below paints — otherwise the first frame measures the anchor
  // while it's still in a hidden panel (0x0 rect) and the popover jumps.
  useLayoutEffect(() => {
    if (step?.mobilePanel) onStepPanel?.(step.mobilePanel);
  }, [step?.mobilePanel, onStepPanel]);

  // Measure the anchored element so we can position the highlight + popover.
  // Re-measure after the panel switch above commits (layout effect runs post-DOM).
  const measure = useCallback(() => {
    const anchor = step?.anchor;
    if (!anchor) {
      setRect(null);
      return;
    }
    // `anchor` may be an ordered fallback list: try each selector and take the
    // first that's actually in the DOM (e.g. the Download button before it
    // exists falls back to the tiers panel).
    const selectors = Array.isArray(anchor) ? anchor : [anchor];
    let el: Element | null = null;
    for (const sel of selectors) {
      el = document.querySelector(sel);
      if (el) break;
    }
    if (!el) {
      // No anchor in the DOM (e.g. element conditionally rendered) — fall back
      // to a centered popover rather than pointing at nothing.
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [step?.anchor]);

  useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure]);

  // Move focus into the popover's primary action on each step.
  useEffect(() => {
    primaryRef.current?.focus();
  }, [stepIndex]);

  // Escape skips; Tab is trapped within the popover.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onSkip();
        return;
      }
      if (e.key === "Tab" && popoverRef.current) {
        const focusables = popoverRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  if (!step) return null;

  // Popover placement: below the highlight when anchored and there's room,
  // otherwise centered. On mobile the popover docks to the bottom.
  const centered = !rect;

  const titleId = "onboarding-tour-title";
  const bodyId = "onboarding-tour-body";

  return (
    <div
      className="fixed inset-0 z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      {/* Dimmed backdrop. Click is a no-op by design. */}
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" />

      {/* Highlight ring around the anchored element. */}
      {rect && (
        <div
          aria-hidden="true"
          className="absolute rounded-lg ring-2 ring-primary ring-offset-2 ring-offset-background transition-all"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.5)",
          }}
        />
      )}

      {/* Popover */}
      <div
        ref={popoverRef}
        className={cn(
          "absolute w-[calc(100%-1.5rem)] max-w-sm rounded-lg border bg-card p-5 shadow-xl",
          centered
            ? "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            : "left-3 right-3 bottom-4 sm:left-auto sm:right-auto sm:bottom-auto mx-auto sm:mx-0",
        )}
        style={
          rect
            ? {
                // Place just below the highlight, clamped into view. Reset
                // bottom/right (set by the mobile-dock classes) to auto so the
                // popover positions by top/left alone — otherwise all four edges
                // are set at once and the box stretches/clamps instead.
                top: Math.min(
                  rect.top + rect.height + PAD + POPOVER_GAP,
                  window.innerHeight - 220,
                ),
                left: Math.min(
                  Math.max(rect.left, 12),
                  window.innerWidth - 360,
                ),
                right: "auto",
                bottom: "auto",
              }
            : undefined
        }
      >
        <Button
          variant="ghost"
          size="icon"
          aria-label="Skip tour"
          onClick={onSkip}
          className="absolute right-2 top-2 h-8 w-8"
        >
          <X className="h-4 w-4" />
        </Button>

        <p className="text-xs font-medium text-muted-foreground">
          Step {stepIndex + 1} of {totalSteps}
        </p>
        <h2 id={titleId} className="mt-1 pr-8 text-base font-semibold text-foreground">
          {step.title}
        </h2>
        <p id={bodyId} className="mt-2 text-sm text-muted-foreground">
          {step.body}
        </p>

        {/* Progress dots */}
        <div className="mt-4 flex items-center gap-1.5" role="group" aria-label="Tour progress">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Go to step ${i + 1}`}
              aria-current={i === stepIndex ? "step" : undefined}
              onClick={() => onGoTo(i)}
              className={cn(
                "h-2 rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                i === stepIndex ? "w-5 bg-primary" : "w-2 bg-muted-foreground/30 hover:bg-muted-foreground/60",
              )}
            />
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onBack}
            disabled={isFirst}
          >
            Back
          </Button>
          <Button ref={primaryRef} size="sm" onClick={onNext}>
            {isFirst ? "Start tour" : isLast ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
