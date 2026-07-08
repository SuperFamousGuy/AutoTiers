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

/**
 * Set `key` to `newValue` (clamped to [0, 100]) and auto-complement the other
 * weight to `100 - newValue`. Because there are exactly two weights, any change
 * has one unambiguous complement, so the result always sums to 100 — keeping the
 * pair valid by construction. Use this for user-driven edits (slider drag, input
 * blur) so the invalid "Sums X%" state is unreachable via normal interaction.
 */
export function setComplementaryWeight(
  key: WeightKey,
  newValue: number,
): Weights {
  const clamped = Math.max(0, Math.min(100, newValue));
  const complement = 100 - clamped;
  return key === "prior"
    ? { prior: clamped, consensus: complement }
    : { prior: complement, consensus: clamped };
}

export function weightsAreValid(w: Weights): boolean {
  return w.prior + w.consensus === 100;
}
