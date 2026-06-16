import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FeedbackDialog } from "@/components/FeedbackDialog";
import { ApiError } from "@/api/client";

const sendFeedbackMock = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/feedback", () => ({
  sendFeedback: (msg: string, category?: string, attachment?: unknown) =>
    sendFeedbackMock(msg, category, attachment),
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

    await waitFor(() =>
      expect(sendFeedbackMock).toHaveBeenCalledWith("hello team", "idea", null),
    );
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

    await waitFor(() =>
      expect(sendFeedbackMock).toHaveBeenCalledWith("quick send", "idea", null),
    );
  });

  it("defaults the category to Idea and sends it", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    // The Idea radio is checked by default.
    expect(screen.getByRole("radio", { name: "Idea" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Bug" })).not.toBeChecked();

    await userEvent.type(screen.getByLabelText("Your feedback"), "default cat");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    await waitFor(() =>
      expect(sendFeedbackMock).toHaveBeenCalledWith("default cat", "idea", null),
    );
  });

  it.each([
    ["Bug", "bug"],
    ["Idea", "idea"],
    ["Other", "other"],
  ])("sends the %s category when selected", async (label, wire) => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    await userEvent.click(screen.getByRole("radio", { name: label }));
    await userEvent.type(screen.getByLabelText("Your feedback"), "tagged");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    await waitFor(() =>
      expect(sendFeedbackMock).toHaveBeenCalledWith("tagged", wire, null),
    );
  });

  it("resets the category back to Idea each time the dialog re-opens", async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <FeedbackDialog open onOpenChange={onOpenChange} userEmail={null} />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "Bug" }));
    expect(screen.getByRole("radio", { name: "Bug" })).toBeChecked();

    // Close then re-open.
    rerender(<FeedbackDialog open={false} onOpenChange={onOpenChange} userEmail={null} />);
    rerender(<FeedbackDialog open onOpenChange={onOpenChange} userEmail={null} />);

    expect(screen.getByRole("radio", { name: "Idea" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Bug" })).not.toBeChecked();
  });


  it("rejects a non-image file with an inline error and does not attach it", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;
    const txt = new File(["hello"], "notes.txt", { type: "text/plain" });
    // accept="" would block this at the browser; bypass to exercise the JS guard
    // that also defends against drag-drop / renamed files.
    await userEvent.upload(input, txt, { applyAccept: false });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/PNG, JPEG, or WebP/i);
    expect(screen.queryByText(/Attached:/i)).not.toBeInTheDocument();
  });

  it("attaches a valid image and sends it as base64", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;
    const png = new File([new Uint8Array([1, 2, 3, 4])], "shot.png", { type: "image/png" });
    await userEvent.upload(input, png);

    expect(await screen.findByText(/Attached: shot.png/i)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Your feedback"), "with image");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    await waitFor(() => expect(sendFeedbackMock).toHaveBeenCalledTimes(1));
    const [msg, cat, attachment] = sendFeedbackMock.mock.calls[0];
    expect(msg).toBe("with image");
    expect(cat).toBe("idea");
    expect(attachment).toMatchObject({ name: "shot.png", type: "image/png" });
    expect(typeof attachment.base64).toBe("string");
    expect(attachment.base64.length).toBeGreaterThan(0);
  });

  it("removes an attached image when Remove is clicked", async () => {
    renderDialog();
    const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;
    const png = new File([new Uint8Array([1, 2, 3, 4])], "shot.png", { type: "image/png" });
    await userEvent.upload(input, png);
    expect(await screen.findByText(/Attached: shot.png/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByText(/Attached:/i)).not.toBeInTheDocument();
  });

  it("sends no attachment when none is selected", async () => {
    sendFeedbackMock.mockResolvedValue(undefined);
    renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "text only");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    await waitFor(() => expect(sendFeedbackMock).toHaveBeenCalledTimes(1));
    const [, , attachment] = sendFeedbackMock.mock.calls[0];
    expect(attachment).toBeNull();
  });

});
