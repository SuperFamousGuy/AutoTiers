export interface Weights {
  prior: number;
  consensus: number;
  adp: number;
}

export type WeightKey = keyof Weights;

/**
 * Adjust one weight to `newValue` and redistribute the delta to the other two
 * weights proportionally to their existing share. If both other weights are
 * zero, split the remainder evenly. Returns integer values that always sum to
 * 100.
 */
export function redistribute(
  changed: WeightKey,
  newValue: number,
  current: Weights,
): Weights {
  const others: WeightKey[] =
    changed === "prior"
      ? ["consensus", "adp"]
      : changed === "consensus"
      ? ["prior", "adp"]
      : ["prior", "consensus"];

  const remaining = 100 - newValue;
  const oldOtherSum = current[others[0]] + current[others[1]];

  let a: number;
  let b: number;
  if (oldOtherSum === 0) {
    a = Math.floor(remaining / 2);
    b = remaining - a;
  } else {
    a = Math.round((current[others[0]] / oldOtherSum) * remaining);
    b = remaining - a;
  }

  return {
    ...current,
    [changed]: newValue,
    [others[0]]: a,
    [others[1]]: b,
  };
}

export function weightsAreValid(w: Weights): boolean {
  return w.prior + w.consensus + w.adp === 100;
}
