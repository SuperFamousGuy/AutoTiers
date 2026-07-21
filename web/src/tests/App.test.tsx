import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

describe("App (integration)", () => {
  it("loads, allows generating, and shows tier results", async () => {
    renderApp();

    // Header renders
    expect(screen.getByText("AutoTiers")).toBeInTheDocument();

    // Rules load from MSW
    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    // Settings panel renders
    expect(screen.getByText(/score weights/i)).toBeInTheDocument();

    // Generate button is enabled (default weights sum to 100)
    const generateButton = screen.getByRole("button", { name: /^generate$/i });
    expect(generateButton).not.toBeDisabled();

    // Click Generate
    const user = userEvent.setup();
    await user.click(generateButton);

    // Tier results render
    await waitFor(() => {
      expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    });
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
  });

  it("defaults a first-run session to Half PPR scoring (#688)", async () => {
    // First-run means no persisted state — clear anything (onboarding, theme)
    // that other tests may have left in localStorage.
    localStorage.clear();
    renderApp();

    // Wait directly on the scoring-format radios rather than an unrelated rule
    // label, so the assertion isn't order-dependent or brittle to fixture changes.
    await waitFor(() => {
      // Half PPR is the shipped first-run default, not Standard.
      expect(screen.getByRole("radio", { name: /Half PPR/i })).toBeChecked();
    });
    expect(screen.getByRole("radio", { name: /^Standard$/i })).not.toBeChecked();
  });

  it("shows a staleness banner after a settings change and clears it on regenerate", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const STALE_TEXT = /settings changed since this list was generated/i;

    // No banner before the first generate.
    expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();

    // Generate once.
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => {
      expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    });
    // No banner immediately after a fresh generate.
    expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();

    // Change an input that flows into the GenerateRequest (a bonus toggle).
    await user.click(screen.getByRole("switch", { name: /100-yd rushing/i }));

    // Banner appears (within one render).
    await waitFor(() => {
      expect(screen.getByText(STALE_TEXT)).toBeInTheDocument();
    });

    // Regenerating from the banner clears it once the fresh result lands.
    // Scope to the staleness banner specifically — the GenerateButton also
    // renders a role="status" live region for its pending announcement.
    const banner = screen.getByText(STALE_TEXT).closest<HTMLElement>("[role='status']")!;
    await user.click(within(banner).getByRole("button", { name: /^generate$/i }));
    await waitFor(() => {
      expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();
    });
  });
});
