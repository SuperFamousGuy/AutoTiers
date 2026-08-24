import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GenerateButton } from "@/components/GenerateButton";

describe("GenerateButton", () => {
  it("renders the Generate label and fires onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<GenerateButton disabled={false} isPending={false} onClick={onClick} />);
    const button = screen.getByRole("button", { name: /generate/i });
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("keeps the live region empty when not pending so it doesn't re-announce", () => {
    render(<GenerateButton disabled={false} isPending={false} onClick={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("does not mark the button busy when not pending", () => {
    render(<GenerateButton disabled={false} isPending={false} onClick={vi.fn()} />);
    expect(screen.getByRole("button", { name: /generate/i })).toHaveAttribute(
      "aria-busy",
      "false",
    );
  });

  it("announces a pending status while generating", () => {
    render(<GenerateButton disabled={false} isPending={true} onClick={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent(/generating/i);
  });

  it("sets aria-busy=true and disables the button while pending", () => {
    render(<GenerateButton disabled={false} isPending={true} onClick={vi.fn()} />);
    const button = screen.getByRole("button", { name: /generate/i });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
  });

  it("surfaces the disabled reason as a title and via aria-describedby (#838)", () => {
    const reason = "Scoring weights must add up to 100%.";
    render(
      <GenerateButton disabled={true} isPending={false} onClick={vi.fn()} disabledReason={reason} />,
    );
    const button = screen.getByRole("button", { name: /generate/i });
    expect(button).toHaveAttribute("title", reason);
    // aria-describedby points at an sr-only span carrying the same text, so
    // keyboard/screen-reader users get parity with the desktop hover tooltip.
    expect(button).toHaveAccessibleDescription(reason);
  });

  it("uses aria-disabled (not native disabled) so the reason stays discoverable (#838)", async () => {
    // A natively-disabled button gets `pointer-events-none` and drops out of the
    // tab order, so its title/aria-describedby are never surfaced. aria-disabled
    // keeps it focusable/hoverable while we block the click ourselves.
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <GenerateButton
        disabled={true}
        isPending={false}
        onClick={onClick}
        disabledReason="Select or create a profile to generate."
      />,
    );
    const button = screen.getByRole("button", { name: /generate/i });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled();
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("uses WCAG-AA amber classes, not the failing amber-500/opacity-70 (#1054)", () => {
    render(<GenerateButton disabled={false} isPending={false} onClick={vi.fn()} />);
    const cls = screen.getByRole("button", { name: /generate/i }).className;
    // Enabled/hover fills that clear 4.5:1 against white text.
    expect(cls).toContain("bg-amber-700");
    expect(cls).toContain("hover:bg-amber-800");
    expect(cls).toContain("text-white");
    // Disabled states darken the fill instead of dimming into a low-contrast blend.
    expect(cls).toContain("disabled:bg-amber-900");
    expect(cls).toContain("aria-disabled:bg-amber-900");
    expect(cls).toContain("disabled:opacity-90");
    expect(cls).toContain("aria-disabled:opacity-90");
    // The reported failing values must be gone. twMerge drops the base
    // disabled:opacity-50 in favor of our opacity-90, so it should not survive.
    expect(cls).not.toContain("bg-amber-500");
    expect(cls).not.toContain("opacity-70");
    expect(cls).not.toContain("opacity-50");
  });

  it("adds no title or description when enabled", () => {
    render(<GenerateButton disabled={false} isPending={false} onClick={vi.fn()} disabledReason={null} />);
    const button = screen.getByRole("button", { name: /generate/i });
    expect(button).not.toHaveAttribute("title");
    expect(button).not.toHaveAttribute("aria-describedby");
  });

  it("does not surface a stale reason while a generate is pending", () => {
    // Pending disables the button too, but the reason is a precondition message —
    // the pending live region owns the in-flight announcement.
    render(
      <GenerateButton
        disabled={false}
        isPending={true}
        onClick={vi.fn()}
        disabledReason="Select or create a profile to generate."
      />,
    );
    const button = screen.getByRole("button", { name: /generate/i });
    expect(button).not.toHaveAttribute("title");
    expect(button).not.toHaveAttribute("aria-describedby");
  });
});
