import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataFreshness } from "@/components/DataFreshness";
import { server } from "@/tests/setup";
import dataStatus from "@/tests/fixtures/data-status.json";
import type { ReactNode } from "react";

const API_URL = "http://localhost:8000";

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

  describe("on a failed /api/data/status fetch", () => {
    it("renders a role=alert error state (not the generic unavailable span) after retries exhaust", async () => {
      // The whole point of the fix: a persistent failure must surface an alert
      // with distinct copy, not the generic non-alert "Data status unavailable".
      // Removing the isError branch drops this test straight back to that span.
      server.use(
        http.get(`${API_URL}/api/data/status`, () => HttpResponse.error()),
      );
      renderWithClient(<DataFreshness />);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/couldn't load data status/i);
      expect(screen.queryByText(/data status unavailable/i)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    it("clicking Retry re-fires the request and recovers once it succeeds", async () => {
      let calls = 0;
      server.use(
        http.get(`${API_URL}/api/data/status`, () => {
          calls += 1;
          // First fetch fails; the post-Retry fetch returns the fixture.
          return calls === 1 ? HttpResponse.error() : HttpResponse.json(dataStatus);
        }),
      );
      renderWithClient(<DataFreshness />);

      const user = userEvent.setup();
      const retry = await screen.findByRole("button", { name: /retry/i });
      const callsBeforeRetry = calls;
      await user.click(retry);

      // Retry re-fires the query (call count grows) and the healthy state renders.
      expect(await screen.findByText(/data updated/i)).toBeInTheDocument();
      expect(calls).toBeGreaterThan(callsBeforeRetry);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
