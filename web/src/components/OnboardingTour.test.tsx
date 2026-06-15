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

  describe("anchored state (highlight + backdrop)", () => {
    // The settings step (index 1) anchors to #panel-settings. JSDOM returns a
    // zero rect by default, so we mount the anchor and stub its rect to exercise
    // the anchored render path — where the "too dark" and "what's pointed at"
    // bugs lived.
    function mountAnchor() {
      const el = document.createElement("div");
      el.id = "panel-settings";
      el.getBoundingClientRect = () =>
        ({ top: 100, left: 100, width: 200, height: 50, right: 300, bottom: 150, x: 100, y: 100, toJSON: () => ({}) }) as DOMRect;
      document.body.appendChild(el);
      return el;
    }

    it("does NOT stack a full-screen black/50 backdrop over the spotlight when anchored (no double-dim)", () => {
      const el = mountAnchor();
      const { container } = render(
        <OnboardingTour
          stepIndex={1}
          totalSteps={TOTAL}
          onNext={vi.fn()}
          onBack={vi.fn()}
          onGoTo={vi.fn()}
          onSkip={vi.fn()}
          onStepPanel={vi.fn()}
        />,
      );
      // The legacy full-screen dim used bg-black/50 on an inset-0 layer. When
      // anchored, that layer must be absent (the spotlight shadow is the only
      // dim) — otherwise the two compose to ~0.75 opacity (the reported bug).
      const fullScreenDim = container.querySelector(".inset-0.bg-black\\/50");
      expect(fullScreenDim).toBeNull();
      // And there should be no bg-black/60 full-screen layer either while anchored.
      const dim60 = container.querySelector(".inset-0.bg-black\\/60");
      expect(dim60).toBeNull();
      el.remove();
    });

    it("renders the connector caret tying the popover to the highlight when anchored", () => {
      const el = mountAnchor();
      const { container } = render(
        <OnboardingTour
          stepIndex={1}
          totalSteps={TOTAL}
          onNext={vi.fn()}
          onBack={vi.fn()}
          onGoTo={vi.fn()}
          onSkip={vi.fn()}
          onStepPanel={vi.fn()}
        />,
      );
      // The caret is a rotated square on the popover edge.
      const caret = container.querySelector(".rotate-45");
      expect(caret).not.toBeNull();
      el.remove();
    });

    it("keeps the full-screen dim for the centered welcome step (no anchor to spotlight)", () => {
      const { container } = render(
        <OnboardingTour
          stepIndex={0}
          totalSteps={TOTAL}
          onNext={vi.fn()}
          onBack={vi.fn()}
          onGoTo={vi.fn()}
          onSkip={vi.fn()}
          onStepPanel={vi.fn()}
        />,
      );
      const dim = container.querySelector(".inset-0");
      expect(dim).not.toBeNull();
      // No caret in the centered state (nothing to point at).
      expect(container.querySelector(".rotate-45")).toBeNull();
    });
  });
});
