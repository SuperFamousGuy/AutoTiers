import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { GenerateButton } from "@/components/GenerateButton";

describe("GenerateButton", () => {
  it("renders the Generate label and fires onClick", () => {
    const onClick = vi.fn();
    render(<GenerateButton disabled={false} isPending={false} onClick={onClick} />);
    const button = screen.getByRole("button", { name: /generate/i });
    button.click();
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
});
