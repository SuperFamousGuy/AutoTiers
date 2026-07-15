import { describe, it, expect, vi } from "vitest";
import { createSingleFlight } from "@/lib/singleFlight";

/** A write whose Nth call can be resolved/rejected on demand. */
function gatedWrite<T>() {
  const calls: Array<{ id: string; payload: T; resolve: () => void; reject: (e: unknown) => void }> = [];
  const fn = vi.fn(
    (id: string, payload: T) =>
      new Promise<void>((resolve, reject) => {
        calls.push({ id, payload, resolve, reject });
      }),
  );
  return { fn, calls };
}

describe("createSingleFlight", () => {
  it("does not start a second write while one is in flight for the same id", async () => {
    const { fn, calls } = gatedWrite<number>();
    const run = createSingleFlight(fn);

    run("p1", 1); // A — starts immediately
    run("p1", 2); // B — queued behind A, not fired

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenLastCalledWith("p1", 1);

    calls[0].resolve(); // A settles → B fires
    await Promise.resolve();
    await Promise.resolve();

    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn).toHaveBeenLastCalledWith("p1", 2);
  });

  it("coalesces intermediate payloads, firing only the latest after the in-flight write", async () => {
    const { fn, calls } = gatedWrite<number>();
    const run = createSingleFlight(fn);

    run("p1", 1); // A — in flight
    run("p1", 2); // queued
    run("p1", 3); // supersedes 2
    run("p1", 4); // supersedes 3 — this is the only one that should fire

    expect(fn).toHaveBeenCalledTimes(1);

    calls[0].resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn).toHaveBeenLastCalledWith("p1", 4);
  });

  it("runs different ids concurrently", () => {
    const { fn } = gatedWrite<number>();
    const run = createSingleFlight(fn);

    run("a", 1);
    run("b", 2);

    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn).toHaveBeenCalledWith("a", 1);
    expect(fn).toHaveBeenCalledWith("b", 2);
  });

  it("settles each caller's promise with its own write's result", async () => {
    const { fn, calls } = gatedWrite<number>();
    const run = createSingleFlight(fn);

    const pA = run("p1", 1);
    const pB = run("p1", 2);
    const superseded = pB; // will be replaced by C before it fires
    const pC = run("p1", 3);

    const err = new Error("boom");
    calls[0].reject(err); // A fails
    await expect(pA).rejects.toBe(err);
    // B was superseded by C before it ever fired → resolves (dropped, not failed).
    await expect(superseded).resolves.toBeUndefined();

    await Promise.resolve();
    calls[1].resolve(); // C succeeds
    await expect(pC).resolves.toBeUndefined();
    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn).toHaveBeenLastCalledWith("p1", 3);
  });

  it("recovers after a failed write and accepts new writes", async () => {
    const { fn, calls } = gatedWrite<number>();
    const run = createSingleFlight(fn);

    const pA = run("p1", 1);
    calls[0].reject(new Error("x"));
    await expect(pA).rejects.toThrow("x");

    const pB = run("p1", 2);
    expect(fn).toHaveBeenCalledTimes(2);
    calls[1].resolve();
    await expect(pB).resolves.toBeUndefined();
  });
});
