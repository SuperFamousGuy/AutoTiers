import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataFreshness } from "@/components/DataFreshness";
import type { ReactNode } from "react";

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DataFreshness", () => {
  it("renders 'Loading data status…' while fetching", async () => {
    renderWithClient(<DataFreshness />);
    expect(screen.getByText(/loading data status/i)).toBeInTheDocument();
  });

  it("renders the oldest source's relative time after load", async () => {
    renderWithClient(<DataFreshness />);
    expect(await screen.findByText(/data updated/i)).toBeInTheDocument();
  });

  it("exposes the trigger as a keyboard-focusable button", async () => {
    renderWithClient(<DataFreshness />);
    // A real <button> so the indicator joins the tab order — a bare <span> is
    // keyboard-unreachable (issue #556).
    const trigger = await screen.findByRole("button", { name: /data updated/i });
    trigger.focus();
    expect(trigger).toHaveFocus();
  });

  it("reveals per-source detail (including errors) when the trigger receives focus", async () => {
    renderWithClient(<DataFreshness />);
    const user = userEvent.setup();
    const trigger = await screen.findByRole("button", { name: /data updated/i });

    await user.tab();
    expect(trigger).toHaveFocus();

    // Radix opens the tooltip on focus; the espn fixture has last_error "HTTP 503".
    const detail = await screen.findAllByText(/error: HTTP 503/i);
    expect(detail.length).toBeGreaterThan(0);
  });
});
