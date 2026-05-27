import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthDialog } from "@/components/AuthDialog";
import { AuthProvider } from "@/contexts/AuthContext";

function _renderOpen() {
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 })); // /me
  return render(
    <AuthProvider>
      <AuthDialog open onOpenChange={() => {}} initialState={null} />
    </AuthProvider>,
  );
}

describe("AuthDialog", () => {
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
});
