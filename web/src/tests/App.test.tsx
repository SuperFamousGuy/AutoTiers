import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
    const banner = screen.getByRole("status");
    await user.click(within(banner).getByRole("button", { name: /^generate$/i }));
    await waitFor(() => {
      expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();
    });
  });
});
