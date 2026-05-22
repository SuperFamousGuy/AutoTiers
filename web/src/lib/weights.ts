export interface Weights {
  prior: number;
  consensus: number;
}

export type WeightKey = keyof Weights;

/**
 * Adjust one weight to `newValue` and move the delta to the other weight.
 * With only two weights, the other simply absorbs `100 - newValue`.
 * Returns integer values that always sum to 100.
 */
export function redistribute(
  changed: WeightKey,
  newValue: number,
  _current: Weights,
): Weights {
  const other: WeightKey = changed === "prior" ? "consensus" : "prior";
  return { [changed]: newValue, [other]: 100 - newValue } as unknown as Weights;
}

export function weightsAreValid(w: Weights): boolean {
  return w.prior + w.consensus === 100;
}
