import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface GenerateButtonProps {
  disabled: boolean;
  isPending: boolean;
  onClick: () => void;
}

export function GenerateButton({ disabled, isPending, onClick }: GenerateButtonProps) {
  return (
    <Button onClick={onClick} disabled={disabled || isPending} size="lg">
      {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      Generate
    </Button>
  );
}
