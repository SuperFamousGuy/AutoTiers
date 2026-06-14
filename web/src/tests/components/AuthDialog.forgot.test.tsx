/**
 * Tests for the new forgot-password flows in AuthDialog:
 *  - "Forgot password?" link appears on the Login tab
 *  - clicking it shows the forgot-password request form
 *  - submitting the form calls POST /api/auth/password/forgot
 *  - success shows the sent confirmation
 *  - "Back to log in" resets the view
 *  - show/hide password toggle works
 *  - password-strength hint fires on the signup tab
 *  - confirm-password mismatch shows an error
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { AuthDialog } from "@/components/AuthDialog";
import { AuthProvider } from "@/contexts/AuthContext";
import { server } from "@/tests/setup";

const API_URL = "http://localhost:8000";

function renderOpen(props?: Partial<React.ComponentProps<typeof AuthDialog>>) {
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
  return render(
    <AuthProvider>
      <AuthDialog open onOpenChange={() => {}} initialState={null} {...props} />
    </AuthProvider>,
  );
}

describe("AuthDialog — forgot password flow", () => {
  afterEach(() => vi.restoreAllMocks());

  it("Login tab shows a 'Forgot password?' link", async () => {
    renderOpen();
    // Wait for dialog to render
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    expect(screen.getByRole("button", { name: /forgot password/i })).toBeInTheDocument();
  });

  it("clicking 'Forgot password?' transitions to the reset-request view", async () => {
    renderOpen();
    const u = userEvent.setup();
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    await u.click(screen.getByRole("button", { name: /forgot password/i }));
    expect(screen.getByText(/reset your password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it("submitting the forgot-password form calls POST /api/auth/password/forgot", async () => {
    const fetchSpy = vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: "If that email is registered, a reset link is on its way." }),
          { status: 202 },
        ),
      );

    renderOpen();
    const u = userEvent.setup();
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    await u.click(screen.getByRole("button", { name: /forgot password/i }));
    await u.type(screen.getByLabelText(/email address/i), "user@example.com");
    await u.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => expect(screen.getByText(/check your inbox/i)).toBeInTheDocument());

    const call = fetchSpy.mock.calls.find((c) => String(c[0]).includes("/api/auth/password/forgot"));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call![1]!.body))).toMatchObject({ email: "user@example.com" });
  });

  it("shows 'Check your inbox' success message after form submit", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: "If that email is registered, a reset link is on its way." }),
          { status: 202 },
        ),
      );

    renderOpen();
    const u = userEvent.setup();
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    await u.click(screen.getByRole("button", { name: /forgot password/i }));
    await u.type(screen.getByLabelText(/email address/i), "x@example.com");
    await u.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
  });

  it("'Back to log in' from reset-request view returns to the login tab", async () => {
    renderOpen();
    const u = userEvent.setup();
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    await u.click(screen.getByRole("button", { name: /forgot password/i }));
    expect(screen.getByText(/reset your password/i)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: /back to log in/i }));
    // Back to login — the password field for login should be visible again.
    expect(document.getElementById("login-password")).toBeInTheDocument();
  });

  it("shows a rate-limit error on 429 from forgot-password endpoint", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Too many requests" }), { status: 429 }),
      );

    renderOpen();
    const u = userEvent.setup();
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    await u.click(screen.getByRole("button", { name: /forgot password/i }));
    await u.type(screen.getByLabelText(/email address/i), "x@example.com");
    await u.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/too many requests/i)).toBeInTheDocument();
  });

  it("initialView='forgot_password' opens directly to the reset-request view", async () => {
    renderOpen({ initialView: "forgot_password" });
    await screen.findByText(/reset your password/i);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });
});

describe("AuthDialog — signup polish", () => {
  afterEach(() => vi.restoreAllMocks());

  it("signup tab shows a confirm-password field", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={() => {}} initialState={null} />
      </AuthProvider>,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /sign up/i }));
    expect(document.getElementById("signup-confirm-password")).toBeInTheDocument();
  });

  it("signup shows 'Passwords do not match' when confirm doesn't match", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={() => {}} initialState={null} />
      </AuthProvider>,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /sign up/i }));
    await u.type(document.getElementById("signup-email")!, "a@b.com");
    await u.type(document.getElementById("signup-password")!, "StrongPass123");
    await u.type(document.getElementById("signup-confirm-password")!, "DifferentPass123");
    await u.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("password strength hint shows when password < 10 chars", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={() => {}} initialState={null} />
      </AuthProvider>,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /sign up/i }));
    const pwInput = document.getElementById("signup-password")!;
    await u.type(pwInput, "short");
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
  });

  it("show/hide toggle on login password input toggles input type", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={() => {}} initialState={null} />
      </AuthProvider>,
    );
    await screen.findByRole("tab", { name: /log in/i, selected: true });
    const pwInput = document.getElementById("login-password") as HTMLInputElement;
    expect(pwInput.type).toBe("password");

    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /show password/i }));
    expect(pwInput.type).toBe("text");

    await u.click(screen.getByRole("button", { name: /hide password/i }));
    expect(pwInput.type).toBe("password");
  });
});
