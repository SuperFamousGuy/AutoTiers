import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
});
