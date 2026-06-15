import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

// Polyfill ResizeObserver for Radix UI components (e.g. Slider) in jsdom.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// ---------------------------------------------------------------------------
// Defence in depth against jsdom's error-cascade hang (radix-ui/primitives#3432)
// ---------------------------------------------------------------------------
// When a focus event listener throws during jsdom's (synchronous) focus dispatch,
// jsdom's reportException() has a re-entrancy guard: an error thrown *while
// another is being reported* bypasses the cancelable window "error" event and is
// forwarded straight to the VirtualConsole. jsdom's default forwarder wraps each
// error as `new Error(msg, { cause: previousError })`, so a cascade builds an
// ever-deeper cause chain; Node's console formatter then recurses that chain and
// overflows the stack (RangeError), spamming errors that the worker serialises to
// the main process and hanging CI for ~14 min.
//
// The primary fix for the *cause* of those throws lives in package.json (a single
// react-focus-scope instance — see there). This handler is belt-and-suspenders:
// it replaces jsdom's default jsdomError forwarder with a bounded one that prints
// only the top-level message and never walks the cause chain, so no future
// listener throw can ever overflow / hang CI. It hides nothing real — genuine test
// failures surface through vitest's own assertion/error handling.
{
  const jsdomInstance = (globalThis as { jsdom?: { virtualConsole?: unknown } }).jsdom;
  const vc = (jsdomInstance?.virtualConsole ??
    (globalThis as { _virtualConsole?: unknown })._virtualConsole) as
    | { removeAllListeners?: (e: string) => void; on?: (e: string, cb: (err: unknown) => void) => void }
    | undefined;
  if (vc && typeof vc.removeAllListeners === "function" && typeof vc.on === "function") {
    vc.removeAllListeners("jsdomError");
    vc.on("jsdomError", (err: unknown) => {
      const message = (err as { message?: string } | null)?.message ?? String(err);
      process.stderr.write(`[jsdomError] ${message.slice(0, 300)}\n`);
    });
  }
}

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// @radix-ui/react-dismissable-layer sets `body.style.pointerEvents = "none"` while
// a dialog or dropdown menu is open and restores it on close. The primary fix for
// the inert-page bug (outside-click close leaving the page unclickable) lives in
// package.json overrides: deduplicate react-dismissable-layer to 1.1.12 and
// react-focus-guards to 1.1.4 so a single DismissableLayerContext singleton is
// shared across react-menu and react-dialog. This afterEach is belt-and-suspenders:
// if a test throws before closing a dialog/menu, the leaked body style persists into
// the next test and fails its first pointer interaction. Reset it unconditionally.
afterEach(() => {
  if (document.body.style.pointerEvents) {
    document.body.style.pointerEvents = "";
  }
});
