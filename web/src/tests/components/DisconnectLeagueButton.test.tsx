import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DisconnectLeagueButton } from "@/components/DisconnectLeagueButton";

describe("DisconnectLeagueButton", () => {
  it("does not disconnect on the first click — reveals Confirm/Cancel with focus on Confirm", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="Sleeper" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    expect(onDisconnect).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: /^confirm disconnect$/i });
    expect(confirm).toHaveFocus();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
  });

  it("labels the trigger with the provider name so each form reads distinctly", () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="ESPN" busy={false} onDisconnect={onDisconnect} />);
    expect(screen.getByRole("button", { name: "Disconnect ESPN" })).toBeInTheDocument();
  });

  it("Confirm fires onDisconnect exactly once", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="CBS" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect cbs/i }));
    await u.click(screen.getByRole("button", { name: /^confirm disconnect$/i }));
    expect(onDisconnect).toHaveBeenCalledTimes(1);
  });

  it("keeps 'Confirm Disconnect' armed after a rejected disconnect so retry is one click (#812)", async () => {
    // The parent owns the error line; here we drive the button directly with a
    // rejecting handler to prove the confirm/busy state survives the failure.
    const onDisconnect = vi.fn().mockRejectedValue(new Error("Disconnect failed."));
    render(<DisconnectLeagueButton provider="Sleeper" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    await u.click(screen.getByRole("button", { name: /^confirm disconnect$/i }));
    expect(onDisconnect).toHaveBeenCalledTimes(1);
    // Immediately after the rejection the pair is still shown — NOT a re-armed
    // plain "Disconnect" that would demand two clicks to retry.
    expect(screen.getByRole("button", { name: /^confirm disconnect$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^disconnect sleeper$/i })).not.toBeInTheDocument();
    // A single additional click retries the unlink — no re-arming needed.
    await u.click(screen.getByRole("button", { name: /^confirm disconnect$/i }));
    expect(onDisconnect).toHaveBeenCalledTimes(2);
  });

  it("Cancel returns to the plain trigger without calling onDisconnect", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="NFL" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect nfl/i }));
    await u.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(onDisconnect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /disconnect nfl/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^confirm disconnect$/i })).not.toBeInTheDocument();
  });

  it("Confirm/Cancel are Tab-reachable and activate on the keyboard (Space confirms)", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="Yahoo" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    // Reveal the pair; focus starts on Confirm. Space activates the focused button.
    await u.click(screen.getByRole("button", { name: /disconnect yahoo/i }));
    expect(screen.getByRole("button", { name: /^confirm disconnect$/i })).toHaveFocus();
    await u.keyboard(" ");
    expect(onDisconnect).toHaveBeenCalledTimes(1);
  });

  it("Enter on the focused Cancel dismisses the confirm without disconnecting", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="Yahoo" busy={false} onDisconnect={onDisconnect} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect yahoo/i }));
    // Tab from Confirm to Cancel, then activate Cancel with Enter.
    await u.tab();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toHaveFocus();
    await u.keyboard("{Enter}");
    expect(onDisconnect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /disconnect yahoo/i })).toBeInTheDocument();
  });

  it("disables the whole affordance while a sibling action is busy", async () => {
    const onDisconnect = vi.fn();
    render(<DisconnectLeagueButton provider="Sleeper" busy={true} onDisconnect={onDisconnect} />);
    const trigger = screen.getByRole("button", { name: /disconnect sleeper/i });
    expect(trigger).toBeDisabled();
  });
});
