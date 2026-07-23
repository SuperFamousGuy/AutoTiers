/**
 * A UUID-v4 generator that works in ANY context — including plain-HTTP
 * origins and older browsers where `crypto.randomUUID` is undefined.
 *
 * `crypto.randomUUID` is specified to exist only in *secure* contexts
 * (HTTPS/localhost); on a plain-HTTP origin it is `undefined`, and on very
 * old browsers `crypto` itself may be missing. Calling it unguarded there
 * throws, and when that throw happens inside a mount effect (the first-run
 * profile auto-create) it is an uncaught, unrecoverable crash for that whole
 * class of visitor (#859).
 *
 * Strategy, in order of preference:
 *  1. Native `crypto.randomUUID()` when available.
 *  2. Cryptographically-random bytes via `crypto.getRandomValues`.
 *  3. `Math.random()` as a last resort so ID generation can never throw.
 */
export function uuidv4(): string {
  const c = typeof crypto !== "undefined" ? crypto : undefined;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }

  // RFC 4122 §4.4: force the version (4) and variant (10xx) bits.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return (
    hex.slice(0, 4).join("") +
    "-" +
    hex.slice(4, 6).join("") +
    "-" +
    hex.slice(6, 8).join("") +
    "-" +
    hex.slice(8, 10).join("") +
    "-" +
    hex.slice(10, 16).join("")
  );
}
