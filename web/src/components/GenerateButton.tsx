import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface GenerateButtonProps {
  disabled: boolean;
  isPending: boolean;
  onClick: () => void;
}

export function GenerateButton({ disabled, isPending, onClick }: GenerateButtonProps) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled || isPending}
      size="lg"
      className="bg-amber-500 hover:bg-amber-600 text-white border-0 disabled:opacity-70"
    >
      {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      Generate
    </Button>
  );
}
