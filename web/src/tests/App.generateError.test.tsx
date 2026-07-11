import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";
import { server } from "./setup";

// Regression guard for #607: a failed /api/generate must surface a distinct,
// announced error affordance (role=alert) + a toast — NOT silently revert to the
// pre-generate "Click Generate…" empty state. These tests reject the request for
// real (a 500 and, separately, a network rejection); they would fail if the
// onError toast wiring or the TiersPanel isError/error wiring were removed.

function renderApp() {
  const client = new QueryClient({
    // Mutations don't retry by default, but pin queries off-retry so the rules
    // fetch (needed to enable Generate) resolves fast and deterministically.
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

async function waitForGenerateEnabled() {
  // Rules must load before Generate is enabled (canonicalRules.length > 0).
  await waitFor(() => {
    expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
  });
}

describe("App — generate failure is surfaced, not swallowed (#607)", () => {
  it("shows a role=alert error affordance and a toast on a 500, not the empty state", async () => {
    server.use(
      http.post("http://localhost:8000/api/generate", () =>
        HttpResponse.text("Internal Server Error", { status: 500 }),
      ),
    );
    renderApp();
    await waitForGenerateEnabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    // In-panel alert names the failure…
    await waitFor(() => {
      expect(screen.getByText(/couldn't generate your tier list/i)).toBeInTheDocument();
    });
    // …the toast fired from onError. Radix mirrors the toast title into a
    // transient screen-reader announce region for ~1s, so the copy can briefly
    // match twice; assert at least one match rather than exactly one.
    expect(screen.getAllByText(/generate failed/i).length).toBeGreaterThan(0);
    // …and the misleading pre-generate copy is gone.
    expect(screen.queryByText(/click generate to build/i)).not.toBeInTheDocument();
  });

  it("shows the error affordance on a network rejection too", async () => {
    server.use(
      http.post("http://localhost:8000/api/generate", () => HttpResponse.error()),
    );
    renderApp();
    await waitForGenerateEnabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() => {
      expect(screen.getByText(/couldn't generate your tier list/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/click generate to build/i)).not.toBeInTheDocument();
  });

  it("Retry re-fires the request and recovers to a rendered tier list on success", async () => {
    let attempt = 0;
    server.use(
      http.post("http://localhost:8000/api/generate", async () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.text("Internal Server Error", { status: 500 });
        }
        const mod = await import("./fixtures/generate-response.json");
        return HttpResponse.json(mod.default);
      }),
    );
    renderApp();
    await waitForGenerateEnabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    const retry = await screen.findByRole("button", { name: /^retry$/i });
    await user.click(retry);

    // The second attempt succeeds — the tier list renders and the error clears.
    await waitFor(() => {
      expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    });
    expect(screen.queryByText(/couldn't generate your tier list/i)).not.toBeInTheDocument();
    expect(attempt).toBe(2);
  });
});
