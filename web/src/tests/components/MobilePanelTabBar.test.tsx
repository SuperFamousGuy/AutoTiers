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
});
