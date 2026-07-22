import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { ToastProvider } from "@/components/ui/toast";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <App />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("App skip-to-main-content link (#811)", () => {
  beforeEach(() => {
    // Mark onboarding as already seen so the first-run tour doesn't auto-start
    // and trap focus in its popover — that would steal the first Tab stop we're
    // asserting on. Orthogonal to the skip link itself.
    localStorage.setItem("onboarding_seen", "1");
  });

  it("renders the skip link targeting the <main> region", () => {
    renderApp();

    const link = screen.getByRole("link", { name: /skip to main content/i });
    expect(link).toHaveAttribute("href", "#main-content");

    // The target region carries the matching id and is focusable so the skip
    // link can move focus onto it programmatically.
    const main = document.getElementById("main-content");
    expect(main?.tagName).toBe("MAIN");
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("is the first focusable element — a single Tab lands on it", async () => {
    renderApp();
    const user = userEvent.setup();

    const link = screen.getByRole("link", { name: /skip to main content/i });
    // Nothing focused on load; the first Tab must reach the skip link before
    // any header control (WCAG 2.4.1 Bypass Blocks).
    await user.tab();
    expect(link).toHaveFocus();
  });

  it("moves focus to the <main> region when activated", async () => {
    renderApp();
    const user = userEvent.setup();

    const link = screen.getByRole("link", { name: /skip to main content/i });
    // Tab to the link (first stop) and activate it — the key acceptance
    // criterion is that focus lands on <main>, not merely that the hash changes.
    await user.tab();
    expect(link).toHaveFocus();
    await user.keyboard("{Enter}");

    const main = document.getElementById("main-content");
    expect(main).toHaveFocus();
  });

  it("stays visually hidden until focused (off-screen, not display:none)", () => {
    renderApp();

    const link = screen.getByRole("link", { name: /skip to main content/i });
    // `sr-only` keeps it off-screen (clip/position) rather than removed from the
    // a11y tree; `focus:not-sr-only` brings it back into view on focus.
    expect(link).toHaveClass("sr-only");
    expect(link.className).toContain("focus:not-sr-only");
  });
});
