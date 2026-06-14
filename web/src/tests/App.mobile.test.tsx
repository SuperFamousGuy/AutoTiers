import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";
import { server } from "./setup";
import generateResponse from "./fixtures/generate-response.json";

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

describe("App mobile tab bar", () => {
  it("renders the mobile panel tab bar with all three tabs", async () => {
    renderApp();
    const tablist = screen.getByRole("tablist", { name: "Panel navigation" });
    expect(tablist).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tiers" })).toBeInTheDocument();
  });

  it("defaults to Settings tab before any generate result", () => {
    renderApp();
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "false");
  });

  it("switches active tab when a tab button is clicked", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Rules" }));
    expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "false");
  });

  it("switches to Tiers tab automatically after generate result arrives", async () => {
    renderApp();

    // Wait for rules to load so generate becomes available
    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    // Default is Settings before generate
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    // After generate result arrives, Tiers tab should be active
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true");
    });
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "false");
  });

  it("all three panels are present in the DOM (desktop layout: all panels always rendered)", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    // Settings panel content
    expect(screen.getByText(/score weights/i)).toBeInTheDocument();
    // Rules panel content (loaded from MSW)
    expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    // Tiers panel content (empty state / placeholder)
    expect(screen.getByRole("tabpanel", { name: "Tiers" })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel", { name: "Rules" })).toBeInTheDocument();
  });

  it("the settings panel wrapper has 'hidden' class when rules tab is active", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Rules" }));

    const settingsPanel = screen.getByRole("tabpanel", { name: "Settings" });
    expect(settingsPanel.className).toContain("hidden");
  });

  it("the rules panel wrapper does not have 'hidden' class when rules tab is active", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Rules" }));

    const rulesPanel = screen.getByRole("tabpanel", { name: "Rules" });
    expect(rulesPanel.className).not.toContain("hidden");
  });

  it("second generate does not auto-switch away from a manually chosen tab", async () => {
    // The auto-switch guard (hasAutoSwitchedToTiers ref) must fire only once.
    // After the first generate switches to Tiers, the user navigates back to
    // Settings; a second generate must leave the tab on Settings.
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // First generate — auto-switches to Tiers
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true");
    });

    // User manually navigates back to Settings
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");

    // Override handler so the second generate returns a new object reference
    // (simulating real TanStack Query v5 behavior where each mutate call
    // replaces mutation.data with a fresh object, re-triggering the effect)
    server.use(
      http.post("http://localhost:8000/api/generate", () =>
        HttpResponse.json({ ...generateResponse }),
      ),
    );

    // Second generate — tab must stay on Settings
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    // Give the effect time to run if it were going to switch
    await waitFor(() => {
      expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "false");
  });
});
