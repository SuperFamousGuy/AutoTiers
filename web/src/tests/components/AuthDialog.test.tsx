import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthDialog } from "@/components/AuthDialog";
import { AuthProvider } from "@/contexts/AuthContext";

const me = {
  user: { id: "u1", email: "a@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: null },
  profiles: [],
};

function _renderOpen(onOpenChange: (open: boolean) => void = () => {}) {
  // First fetch: /me on AuthProvider mount → 401 (anonymous)
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
  return render(
    <AuthProvider>
      <AuthDialog open onOpenChange={onOpenChange} initialState={null} />
    </AuthProvider>,
  );
}

describe("AuthDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders Log in tab by default with email + password fields", async () => {
    _renderOpen();
    expect(await screen.findByRole("tab", { name: /log in/i, selected: true })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("switches to Sign up tab when clicked", async () => {
    _renderOpen();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /sign up/i }));
    expect(screen.getByRole("tab", { name: /sign up/i, selected: true })).toBeInTheDocument();
  });

  it("shows 'Continue with Yahoo' button", async () => {
    _renderOpen();
    const btn = await screen.findByRole("button", { name: /continue with yahoo/i });
    expect(btn).toBeInTheDocument();
  });

  it("shows 'Continue with Google' button", async () => {
    _renderOpen();
    const btn = await screen.findByRole("button", { name: /continue with google/i });
    expect(btn).toBeInTheDocument();
  });

  it("submitting the login form calls /api/auth/login and closes the dialog on success", async () => {
    const onOpenChange = vi.fn();
    const fetchSpy = vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 })); // login

    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={onOpenChange} initialState={null} />
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /^log in$/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));

    const loginCall = fetchSpy.mock.calls.find((c) => String(c[0]).includes("/api/auth/login"));
    expect(loginCall).toBeDefined();
    expect(JSON.parse(String(loginCall![1]!.body))).toMatchObject({
      email: "a@b.com",
      password: "correct horse battery",
    });
  });

  it("login form shows an error message when the API returns 401", async () => {
    const onOpenChange = vi.fn();
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(new Response("bad credentials", { status: 401 })); // login

    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={onOpenChange} initialState={null} />
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /^log in$/i }));

    expect(await screen.findByText(/login failed/i)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("submitting the sign-up form posts current state for migration", async () => {
    const onOpenChange = vi.fn();
    const fetchSpy = vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 201 })); // signup

    const initialState = {
      settings: { scoring_format: "ppr" } as any,
      rules: [{ name: "Test Rule" } as any],
    };

    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={onOpenChange} initialState={initialState} />
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /sign up/i }));
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));

    const signupCall = fetchSpy.mock.calls.find((c) => String(c[0]).includes("/api/auth/signup"));
    expect(signupCall).toBeDefined();
    const body = JSON.parse(String(signupCall![1]!.body));
    expect(body).toMatchObject({
      email: "new@example.com",
      password: "correct horse battery",
      initial_settings: { scoring_format: "ppr" },
      initial_rules: [{ name: "Test Rule" }],
    });
  });

  it("sign-up form shows an error message when the API returns 409", async () => {
    const onOpenChange = vi.fn();
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(new Response("Email already in use", { status: 409 })); // signup

    render(
      <AuthProvider>
        <AuthDialog open onOpenChange={onOpenChange} initialState={null} />
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /sign up/i }));
    await user.type(screen.getByLabelText(/email/i), "taken@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/signup failed/i)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
