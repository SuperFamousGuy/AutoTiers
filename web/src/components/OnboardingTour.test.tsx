import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OnboardingTour } from "@/components/OnboardingTour";
import { ONBOARDING_STEPS } from "@/lib/onboardingSteps";

const TOTAL = ONBOARDING_STEPS.length;

function setup(stepIndex: number, overrides: Partial<Parameters<typeof OnboardingTour>[0]> = {}) {
  const props = {
    stepIndex,
    totalSteps: TOTAL,
    onNext: vi.fn(),
    onBack: vi.fn(),
    onGoTo: vi.fn(),
    onSkip: vi.fn(),
    onStepPanel: vi.fn(),
    ...overrides,
  };
  render(<OnboardingTour {...props} />);
  return props;
}

describe("OnboardingTour", () => {
  it("renders as a modal dialog with the current step's title and body", () => {
    setup(0);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("heading", { name: /welcome to autotiers/i })).toBeInTheDocument();
    expect(screen.getByText(/build your first draft tier list/i)).toBeInTheDocument();
  });

  it("shows step position 'Step 1 of N'", () => {
    setup(0);
    expect(screen.getByText(`Step 1 of ${TOTAL}`)).toBeInTheDocument();
  });

  it("primary button reads 'Start tour' on the first step and calls onNext", async () => {
    const { onNext } = setup(0);
    const btn = screen.getByRole("button", { name: /start tour/i });
    await userEvent.click(btn);
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("primary button reads 'Finish' on the last step", () => {
    setup(TOTAL - 1);
    expect(screen.getByRole("button", { name: /finish/i })).toBeInTheDocument();
  });

  it("primary button reads 'Next' on a middle step", () => {
    setup(2);
    expect(screen.getByRole("button", { name: /^next$/i })).toBeInTheDocument();
  });

  it("Back is disabled on the first step and enabled later", () => {
    const { rerender } = render(
      <OnboardingTour
        stepIndex={0}
        totalSteps={TOTAL}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onGoTo={vi.fn()}
        onSkip={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /back/i })).toBeDisabled();
    rerender(
      <OnboardingTour
        stepIndex={1}
        totalSteps={TOTAL}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onGoTo={vi.fn()}
        onSkip={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /back/i })).not.toBeDisabled();
  });

  it("Back calls onBack", async () => {
    const { onBack } = setup(2);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("the X button skips the tour", async () => {
    const { onSkip } = setup(1);
    await userEvent.click(screen.getByRole("button", { name: /skip tour/i }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("Escape skips the tour", async () => {
    const { onSkip } = setup(1);
    await userEvent.keyboard("{Escape}");
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("renders a progress dot per step and clicking one calls onGoTo", async () => {
    const { onGoTo } = setup(0);
    const dots = screen.getAllByRole("button", { name: /go to step/i });
    expect(dots).toHaveLength(TOTAL);
    await userEvent.click(dots[3]);
    expect(onGoTo).toHaveBeenCalledWith(3);
  });

  it("marks the current step's dot with aria-current", () => {
    setup(2);
    const dots = screen.getAllByRole("button", { name: /go to step/i });
    expect(dots[2]).toHaveAttribute("aria-current", "step");
    expect(dots[0]).not.toHaveAttribute("aria-current");
  });

  it("moves focus to the primary action on mount (keyboard users land in the popover)", () => {
    setup(0);
    expect(screen.getByRole("button", { name: /start tour/i })).toHaveFocus();
  });

  it("requests the matching mobile panel on entering an anchored step", () => {
    // step index 1 is the Settings step -> should ask the parent to show "settings"
    const { onStepPanel } = setup(1);
    expect(onStepPanel).toHaveBeenCalledWith("settings");
  });

  it("does not request a panel switch for the centered welcome step", () => {
    const { onStepPanel } = setup(0);
    expect(onStepPanel).not.toHaveBeenCalled();
  });
});
