import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FeedbackDialog } from "@/components/FeedbackDialog";
import { ApiError } from "@/api/client";

const sendFeedbackMock = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/feedback", () => ({
  sendFeedback: (msg: string) => sendFeedbackMock(msg),
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

function renderDialog(props: Partial<React.ComponentProps<typeof FeedbackDialog>> = {}) {
  const onOpenChange = vi.fn();
  render(
    <FeedbackDialog open onOpenChange={onOpenChange} userEmail={null} {...props} />,
  );
  return { onOpenChange };
}

describe("FeedbackDialog", () => {
  beforeEach(() => {
    sendFeedbackMock.mockReset();
    toastMock.mockReset();
  });

  it("disables Send until the message is non-empty (and whitespace doesn't count)", async () => {
    renderDialog();
    const send = screen.getByRole("button", { name: "Send Feedback" });
    expect(send).toBeDisabled();

    const textarea = screen.getByLabelText("Your feedback");
    await userEvent.type(textarea, "   ");
    expect(send).toBeDisabled();

    await userEvent.type(textarea, "real text");
    expect(send).toBeEnabled();
  });

  it("sends trimmed feedback, toasts success, and closes on success", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    const { onOpenChange } = renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "  hello team  ");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    await waitFor(() => expect(sendFeedbackMock).toHaveBeenCalledWith("hello team"));
    expect(toastMock).toHaveBeenCalledWith({
      title: "Thanks for the feedback!",
      variant: "success",
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows an alert error and stays open when the send fails", async () => {
    sendFeedbackMock.mockRejectedValue(new ApiError(502, "down"));
    const { onOpenChange } = renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "will fail");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/try again/i);
    // Dialog was not asked to close.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("shows the rate-limit message on 429", async () => {
    sendFeedbackMock.mockRejectedValue(new ApiError(429, "slow down"));
    renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "spam");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too quickly/i);
  });

  it("discloses email capture when the user is logged in", () => {
    renderDialog({ userEmail: "alice@example.com" });
    expect(screen.getByText(/include your email \(alice@example.com\)/i)).toBeInTheDocument();
  });

  it("says anonymous when the user is logged out", () => {
    renderDialog({ userEmail: null });
    expect(screen.getByText(/this is anonymous/i)).toBeInTheDocument();
  });

  it("submits with Cmd/Ctrl+Enter", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    const textarea = screen.getByLabelText("Your feedback");
    await userEvent.type(textarea, "quick send");
    await userEvent.keyboard("{Control>}{Enter}{/Control}");

    await waitFor(() => expect(sendFeedbackMock).toHaveBeenCalledWith("quick send"));
  });
});
