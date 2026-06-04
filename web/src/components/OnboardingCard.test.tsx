import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OnboardingCard } from "@/components/OnboardingCard";

describe("OnboardingCard", () => {
  it("renders the welcome heading and the three steps", () => {
    render(<OnboardingCard onDismiss={() => {}} />);
    expect(screen.getByRole("region", { name: /getting started/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /welcome to autotiers/i })).toBeInTheDocument();
    expect(screen.getByText(/Settings/)).toBeInTheDocument();
    expect(screen.getByText(/Rules/)).toBeInTheDocument();
    expect(screen.getByText(/Generate/)).toBeInTheDocument();
  });

  it("calls onDismiss when 'Got it' is clicked", async () => {
    const onDismiss = vi.fn();
    render(<OnboardingCard onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: /got it/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("calls onDismiss when the X close button is clicked", async () => {
    const onDismiss = vi.fn();
    render(<OnboardingCard onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: /dismiss getting-started guide/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("calls onDismiss when Escape is pressed", async () => {
    const onDismiss = vi.fn();
    render(<OnboardingCard onDismiss={onDismiss} />);
    await userEvent.keyboard("{Escape}");
    expect(onDismiss).toHaveBeenCalled();
  });

  it("moves focus to the close button on mount (keyboard users land in the card)", () => {
    render(<OnboardingCard onDismiss={() => {}} />);
    expect(screen.getByRole("button", { name: /dismiss getting-started guide/i })).toHaveFocus();
  });
});
