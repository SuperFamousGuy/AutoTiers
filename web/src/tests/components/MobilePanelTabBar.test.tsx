import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobilePanelTabBar } from "@/components/MobilePanelTabBar";

describe("MobilePanelTabBar", () => {
  it("renders all three tab buttons", () => {
    render(<MobilePanelTabBar active="settings" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tiers" })).toBeInTheDocument();
  });

  it("marks the active tab as aria-selected=true", () => {
    render(<MobilePanelTabBar active="rules" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Rules" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "false");
  });

  it("calls onChange with the clicked tab id", async () => {
    const onChange = vi.fn();
    render(<MobilePanelTabBar active="settings" onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Tiers" }));
    expect(onChange).toHaveBeenCalledWith("tiers");
  });

  it("calls onChange with 'rules' when Rules tab is clicked", async () => {
    const onChange = vi.fn();
    render(<MobilePanelTabBar active="settings" onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Rules" }));
    expect(onChange).toHaveBeenCalledWith("rules");
  });

  it("calls onChange with 'settings' when Settings tab is clicked", async () => {
    const onChange = vi.fn();
    render(<MobilePanelTabBar active="tiers" onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    expect(onChange).toHaveBeenCalledWith("settings");
  });

  it("renders a tablist container with accessible label", () => {
    render(<MobilePanelTabBar active="settings" onChange={() => {}} />);
    expect(screen.getByRole("tablist", { name: "Panel navigation" })).toBeInTheDocument();
  });

  it("switching tabs updates aria-selected when active prop changes", () => {
    const { rerender } = render(<MobilePanelTabBar active="settings" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");

    rerender(<MobilePanelTabBar active="tiers" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Tiers" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "false");
  });

  it("shows no busy affordance when generateIsPending is false", () => {
    render(<MobilePanelTabBar active="settings" onChange={() => {}} generateIsPending={false} />);
    expect(screen.getByRole("tab", { name: "Tiers" })).not.toHaveAttribute("aria-busy", "true");
    expect(screen.queryByTestId("tiers-busy-indicator")).not.toBeInTheDocument();
  });

  it("marks the Tiers tab aria-busy and shows a visible indicator while pending", () => {
    render(<MobilePanelTabBar active="settings" onChange={() => {}} generateIsPending />);
    const tiersTab = screen.getByRole("tab", { name: /Tiers/ });
    expect(tiersTab).toHaveAttribute("aria-busy", "true");
    // The affordance is a visible element, not just a color change.
    expect(screen.getByTestId("tiers-busy-indicator")).toBeInTheDocument();
  });

  it("only the Tiers tab gets the busy affordance while pending", () => {
    render(<MobilePanelTabBar active="settings" onChange={() => {}} generateIsPending />);
    expect(screen.getByRole("tab", { name: "Settings" })).not.toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("tab", { name: "Rules" })).not.toHaveAttribute("aria-busy", "true");
  });

  it("announces via a live region while pending and clears it afterward", () => {
    const { rerender } = render(
      <MobilePanelTabBar active="settings" onChange={() => {}} generateIsPending />,
    );
    const status = screen.getByTestId("tiers-live-region");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Generating tiers…");

    // On success/error the pending flag clears; the affordance and message disappear.
    rerender(<MobilePanelTabBar active="settings" onChange={() => {}} generateIsPending={false} />);
    expect(screen.getByTestId("tiers-live-region")).toHaveTextContent("");
    expect(screen.queryByTestId("tiers-busy-indicator")).not.toBeInTheDocument();
  });
});
