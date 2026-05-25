import { useState, useEffect } from "react";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { setWeight, weightsAreValid, type Weights, type WeightKey } from "@/lib/weights";
import { cn } from "@/lib/utils";

interface ScoreWeightsProps {
  weights: Weights;
  onChange: (next: Weights) => void;
}

const ROWS: { key: WeightKey; label: string }[] = [
  { key: "prior", label: "Prior year actuals" },
  { key: "consensus", label: "Projection" },
  { key: "adp", label: "Market ADP" },
];

interface WeightRowProps {
  weightKey: WeightKey;
  label: string;
  value: number;
  onCommit: (v: number) => void;
}

function WeightRow({ weightKey: _weightKey, label, value, onCommit }: WeightRowProps) {
  const [inputValue, setInputValue] = useState<string>(String(value));

  // Keep input in sync with external changes.
  useEffect(() => {
    setInputValue(String(value));
  }, [value]);

  const handleInputChange = (raw: string) => {
    setInputValue(raw);
    if (raw === "") return; // allow temporarily empty while typing
    const parsed = parseInt(raw, 10);
    if (Number.isNaN(parsed)) return;
    const clamped = Math.max(0, Math.min(100, parsed));
    onCommit(clamped);
  };

  const handleBlur = () => {
    // If left empty or invalid, snap back to the current value.
    if (inputValue === "" || Number.isNaN(parseInt(inputValue, 10))) {
      setInputValue(String(value));
    }
  };

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center text-xs text-muted-foreground">
        <span>{label}</span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            max={100}
            step={1}
            value={inputValue}
            onChange={(e) => handleInputChange(e.target.value)}
            onBlur={handleBlur}
            className="w-12 h-6 text-right font-mono rounded border border-input bg-background px-1 text-foreground"
            aria-label={`${label} percentage`}
          />
          <span>%</span>
        </div>
      </div>
      <Slider
        value={[value]}
        min={0}
        max={100}
        step={1}
        onValueChange={([v]) => onCommit(v)}
        aria-label={label}
      />
    </div>
  );
}

export function ScoreWeights({ weights, onChange }: ScoreWeightsProps) {
  const valid = weightsAreValid(weights);

  return (
    <div className="space-y-3">
      <Label>Score weights</Label>
      {ROWS.map(({ key, label }) => (
        <WeightRow
          key={key}
          weightKey={key}
          label={label}
          value={weights[key]}
          onCommit={(v) => onChange(setWeight(key, v, weights))}
        />
      ))}
      <div className={cn("text-xs font-medium", valid ? "text-green-600" : "text-red-600")}>
        {valid ? "✓ Sums 100%" : `✗ Sums ${weights.prior + weights.consensus + weights.adp}% — adjust to total 100% before generating`}
      </div>
    </div>
  );
}
