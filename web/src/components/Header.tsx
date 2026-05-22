import { DataFreshness } from "./DataFreshness";
import { GenerateButton } from "./GenerateButton";

interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
}

export function Header({ generateDisabled, generateIsPending, onGenerate }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-baseline gap-6">
        <h1 className="text-2xl font-bold text-foreground">AutoTiers</h1>
        <DataFreshness />
      </div>
      <GenerateButton
        disabled={generateDisabled}
        isPending={generateIsPending}
        onClick={onGenerate}
      />
    </header>
  );
}
