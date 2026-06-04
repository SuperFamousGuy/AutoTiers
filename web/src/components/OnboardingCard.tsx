import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface OnboardingCardProps {
  onDismiss: () => void;
}

const STEPS = [
  { n: 1, text: "Set your league's scoring and size in Settings." },
  { n: 2, text: "Pick which rules to weight in Rules." },
  { n: 3, text: "Hit Generate to build your tiers — then download the CSV." },
];

/**
 * First-run guidance. A dismissible welcome card that explains the three-step
 * flow. Rendered above the main panels by App when useOnboarding says so.
 *
 * Accessibility:
 *  - Labelled region so screen readers announce it as "Getting started".
 *  - Moves focus to the dismiss control on mount so keyboard users land here.
 *  - Escape dismisses, matching dialog conventions elsewhere in the app.
 */
export function OnboardingCard({ onDismiss }: OnboardingCardProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <section
      role="region"
      aria-label="Getting started"
      className="relative border-b bg-accent/40 px-6 py-4"
    >
      <Button
        ref={closeRef}
        variant="ghost"
        size="icon"
        aria-label="Dismiss getting-started guide"
        onClick={onDismiss}
        className="absolute right-3 top-3 h-8 w-8"
      >
        <X className="h-4 w-4" />
      </Button>
      <div className="pr-10">
        <h2 className="text-base font-semibold text-foreground">Welcome to AutoTiers</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Build your draft tier list in three steps:
        </p>
        <ol className="mt-2 space-y-1">
          {STEPS.map((s) => (
            <li key={s.n} className="flex items-start gap-2 text-sm text-foreground">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
              >
                {s.n}
              </span>
              <span>{s.text}</span>
            </li>
          ))}
        </ol>
        <div className="mt-3">
          <Button size="sm" onClick={onDismiss}>
            Got it
          </Button>
        </div>
      </div>
    </section>
  );
}
