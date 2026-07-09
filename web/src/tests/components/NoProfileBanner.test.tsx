/**
 * Tests for NoProfileBanner — the zero-profile autosave-disabled warning (#606).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoProfileBanner } from "@/components/NoProfileBanner";

describe("NoProfileBanner", () => {
  it("warns that changes won't be saved", () => {
    render(<NoProfileBanner onCreateProfile={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/changes won.t be saved/i);
  });

  it("has no dismiss control (persistent)", () => {
    render(<NoProfileBanner onCreateProfile={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
  });

  it("calls onCreateProfile when the button is clicked", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<NoProfileBanner onCreateProfile={onCreate} />);
    await userEvent.click(screen.getByRole("button", { name: /create profile/i }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("disables the button while creating, then re-enables it on failure", async () => {
    // Hold onCreateProfile pending so we can observe the in-flight state before
    // it settles — this is what proves the "disable while creating" logic runs.
    let reject!: (e: Error) => void;
    const pending = new Promise<void>((_, r) => {
      reject = r;
    });
    const onCreate = vi.fn().mockReturnValue(pending);
    render(<NoProfileBanner onCreateProfile={onCreate} />);
    const button = screen.getByRole("button", { name: /create profile/i });
    await userEvent.click(button);
    // While the promise is pending the button is disabled and shows progress.
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent(/creating/i);
    reject(new Error("boom"));
    // After the rejected promise settles the button becomes usable again.
    await waitFor(() => expect(button).toBeEnabled());
    expect(onCreate).toHaveBeenCalledTimes(1);
  });
});
