import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";

describe("Auth integration", () => {
  it("anonymous user can open the auth dialog from the hamburger menu", async () => {
    // Mock all the API calls the app makes on first load
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) return new Response("", { status: 401 });
      if (url.includes("/api/rules")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.includes("/api/data/status")) return new Response(JSON.stringify({}), { status: 200 });
      return new Response("", { status: 404 });
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AuthProvider>
      </QueryClientProvider>,
    );

    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));
    await user.click(screen.getByText(/log in \/ sign up/i));
    expect(await screen.findByRole("tab", { name: /sign up/i })).toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
