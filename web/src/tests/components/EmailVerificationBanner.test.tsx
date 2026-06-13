/**
 * Tests for EmailVerificationBanner.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { EmailVerificationBanner } from "@/components/EmailVerificationBanner";
import { server } from "@/tests/setup";

const API_URL = "http://localhost:8000";

describe("EmailVerificationBanner", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the user's email address", () => {
    render(<EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />);
    expect(screen.getByText(/test@example.com/i)).toBeInTheDocument();
  });

  it("shows a Resend button", () => {
    render(<EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />);
    expect(screen.getByRole("button", { name: /resend/i })).toBeInTheDocument();
  });

  it("shows a dismiss button", () => {
    render(<EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />);
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeInTheDocument();
  });

  it("calls onDismiss when the dismiss button is clicked", async () => {
    const onDismiss = vi.fn();
    render(<EmailVerificationBanner email="test@example.com" onDismiss={onDismiss} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("calls POST /api/auth/email/resend-verification when Resend is clicked", async () => {
    // The MSW handler returns 202 by default.
    render(<EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /resend/i }));
    // After success, confirmation message appears.
    expect(await screen.findByText(/verification email sent/i)).toBeInTheDocument();
  });

  it("shows rate-limit message on 429 from resend endpoint", async () => {
    server.use(
      http.post(`${API_URL}/api/auth/email/resend-verification`, () =>
        HttpResponse.json({ detail: "Too many requests" }, { status: 429 }),
      ),
    );
    render(<EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /resend/i }));
    expect(await screen.findByText(/please wait a minute/i)).toBeInTheDocument();
  });

  it("banner has role='status'", () => {
    const { container } = render(
      <EmailVerificationBanner email="test@example.com" onDismiss={() => {}} />,
    );
    expect(container.firstChild).toHaveAttribute("role", "status");
  });
});
