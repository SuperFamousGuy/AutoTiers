import { afterEach, describe, expect, it, vi } from "vitest";
import { uuidv4 } from "./uuid";

const V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/**
 * Temporarily replace a property on `crypto` (restored after the callback),
 * simulating an insecure context where `randomUUID` / `getRandomValues` are
 * `undefined` rather than functions.
 */
function withCryptoProp<T>(
  prop: "randomUUID" | "getRandomValues",
  value: unknown,
  fn: () => T,
): T {
  const desc = Object.getOwnPropertyDescriptor(crypto, prop);
  Object.defineProperty(crypto, prop, {
    value,
    configurable: true,
    writable: true,
  });
  try {
    return fn();
  } finally {
    if (desc) Object.defineProperty(crypto, prop, desc);
    else delete (crypto as unknown as Record<string, unknown>)[prop];
  }
}

afterEach(() => vi.restoreAllMocks());

describe("uuidv4", () => {
  it("returns the native randomUUID when available", () => {
    const spy = vi
      .spyOn(crypto, "randomUUID")
      .mockReturnValue("11111111-1111-4111-8111-111111111111");
    expect(uuidv4()).toBe("11111111-1111-4111-8111-111111111111");
    expect(spy).toHaveBeenCalled();
  });

  it("falls back to a valid v4 id when randomUUID is undefined (insecure context)", () => {
    withCryptoProp("randomUUID", undefined, () => {
      expect(uuidv4()).toMatch(V4_RE);
    });
  });

  it("produces unique ids across many fallback calls", () => {
    withCryptoProp("randomUUID", undefined, () => {
      const ids = new Set(Array.from({ length: 1000 }, () => uuidv4()));
      expect(ids.size).toBe(1000);
    });
  });

  it("still generates a valid id when getRandomValues is also missing", () => {
    withCryptoProp("randomUUID", undefined, () => {
      withCryptoProp("getRandomValues", undefined, () => {
        expect(uuidv4()).toMatch(V4_RE);
      });
    });
  });
});
