import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { redistribute, weightsAreValid, type Weights, type WeightKey } from "@/lib/weights";
import { cn } from "@/lib/utils";

interface ScoreWeightsProps {
  weights: Weights;
  onChange: (next: Weights) => void;
}

const ROWS: { key: WeightKey; label: string }[] = [
  { key: "prior", label: "Prior year actuals" },
  { key: "espn", label: "ESPN projection" },
  { key: "consensus", label: "FantasyPros consensus" },
];

export function ScoreWeights({ weights, onChange }: ScoreWeightsProps) {
  const valid = weightsAreValid(weights);

  return (
    <div className="space-y-3">
      <Label>Score weights</Label>
      {ROWS.map(({ key, label }) => (
        <div key={key} className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{label}</span>
            <span className="font-mono">{weights[key]}%</span>
          </div>
          <Slider
            value={[weights[key]]}
            min={0}
            max={100}
            step={1}
            onValueChange={([v]) => onChange(redistribute(key, v, weights))}
            aria-label={label}
          />
        </div>
      ))}
      <div className={cn("text-xs", valid ? "text-green-600" : "text-red-600")}>
        {valid ? "✓ Sums 100%" : `✗ Sums ${weights.prior + weights.espn + weights.consensus}% (must be 100%)`}
      </div>
    </div>
  );
}
