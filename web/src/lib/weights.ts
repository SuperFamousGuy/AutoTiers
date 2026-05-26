export interface Weights {
  prior: number;
  consensus: number;
}

export type WeightKey = keyof Weights;

/**
 * Set a single weight to `newValue`, clamped to [0, 100]. Does NOT touch the
 * other weights — sliders are independent. Use `weightsAreValid` to check
 * whether the resulting set sums to 100 (required by the backend validator).
 */
export function setWeight(
  key: WeightKey,
  newValue: number,
  current: Weights,
): Weights {
  const clamped = Math.max(0, Math.min(100, newValue));
  return { ...current, [key]: clamped };
}

export function weightsAreValid(w: Weights): boolean {
  return w.prior + w.consensus === 100;
}
