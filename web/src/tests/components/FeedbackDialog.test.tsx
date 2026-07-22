import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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
    <FeedbackDialog open onOpenChange={onOpenChange} {...props} />,
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

  it("discloses that submission is anonymous", () => {
    renderDialog();
    expect(screen.getByText(/sent anonymously/i)).toBeInTheDocument();
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
      <FeedbackDialog open onOpenChange={onOpenChange} />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "Bug" }));
    expect(screen.getByRole("radio", { name: "Bug" })).toBeChecked();

    // Close then re-open.
    rerender(<FeedbackDialog open={false} onOpenChange={onOpenChange} />);
    rerender(<FeedbackDialog open onOpenChange={onOpenChange} />);

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
    // Exact raw base64 of the bytes [1,2,3,4], with NO data-URL prefix — this
    // is the wire contract the backend decodes.
    expect(attachment).toEqual({ name: "shot.png", type: "image/png", base64: "AQIDBA==" });
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

  it("clears the attachment when a change event carries no file", async () => {
    renderDialog();
    const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;

    // Attach first, then fire a change with an empty file list (cancelled picker).
    const png = new File([new Uint8Array([1, 2, 3, 4])], "shot.png", { type: "image/png" });
    await userEvent.upload(input, png);
    expect(await screen.findByText(/Attached: shot.png/i)).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [] } });
    await waitFor(() =>
      expect(screen.queryByText(/Attached:/i)).not.toBeInTheDocument(),
    );
  });

  it("rejects an image larger than 2 MB without attaching it", async () => {
    renderDialog();
    const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;

    const big = new File([new Uint8Array([1, 2, 3, 4])], "huge.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 2 * 1024 * 1024 + 1 });
    await userEvent.upload(input, big);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/under 2 MB/i);
    expect(screen.queryByText(/Attached:/i)).not.toBeInTheDocument();
  });

  it("shows a read error when the file cannot be read", async () => {
    const spy = vi
      .spyOn(FileReader.prototype, "readAsDataURL")
      .mockImplementation(function (this: FileReader) {
        // Simulate a read failure: the dialog rejects and surfaces an error.
        this.onerror?.(new ProgressEvent("error") as ProgressEvent<FileReader>);
      });
    try {
      renderDialog();
      const input = screen.getByLabelText("Attach screenshot (optional)") as HTMLInputElement;
      const png = new File([new Uint8Array([1, 2, 3, 4])], "shot.png", { type: "image/png" });
      await userEvent.upload(input, png);

      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toMatch(/couldn't read that image/i);
      expect(screen.queryByText(/Attached:/i)).not.toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });

  it("shows the generic image-rejected message on a 422 with a non-JSON body", async () => {
    sendFeedbackMock.mockRejectedValue(new ApiError(422, "bad image"));
    renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "image fails server-side");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/couldn't be accepted/i);
  });

  it("surfaces the backend detail string on a 422 with a JSON body", async () => {
    sendFeedbackMock.mockRejectedValue(
      new ApiError(422, JSON.stringify({ detail: "Screenshot metadata supplied without image data." })),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText("Your feedback"), "metadata only");
    await userEvent.click(screen.getByRole("button", { name: "Send Feedback" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/metadata supplied without image data/i);
  });

});
