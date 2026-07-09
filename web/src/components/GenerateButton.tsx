import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface GenerateButtonProps {
  disabled: boolean;
  isPending: boolean;
  onClick: () => void;
}

export function GenerateButton({ disabled, isPending, onClick }: GenerateButtonProps) {
  return (
    <>
      <Button
        data-tour="generate"
        onClick={onClick}
        disabled={disabled || isPending}
        aria-busy={isPending}
        size="default"
        className="bg-amber-500 hover:bg-amber-600 text-white border-0 disabled:opacity-70 lg:h-11 lg:px-8 lg:text-base"
      >
        {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        Generate
      </Button>
      <span role="status" aria-live="polite" className="sr-only">
        {isPending ? "Generating tier list…" : ""}
      </span>
    </>
  );
}
