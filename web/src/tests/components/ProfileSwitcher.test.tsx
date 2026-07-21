import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileSwitcher } from "@/components/ProfileSwitcher";

const profiles = [
  { id: "p1", name: "PPR 12-team", settings: {}, rules: {} },
  { id: "p2", name: "Standard Keeper", settings: {}, rules: {} },
];

describe("ProfileSwitcher", () => {
  it("renders the active profile name in the trigger", () => {
    render(<ProfileSwitcher profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />);
    expect(screen.getByRole("button", { name: /PPR 12-team/ })).toBeInTheDocument();
  });

  it("renders 'No profile' in the trigger when there is no active profile", () => {
    render(<ProfileSwitcher profiles={[]} activeId={null} onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />);
    expect(screen.getByRole("button", { name: /No profile/ })).toBeInTheDocument();
  });

  it("calls onSelect when another profile is clicked", async () => {
    const onSelect = vi.fn();
    render(<ProfileSwitcher profiles={profiles} activeId="p1" onSelect={onSelect} onNew={() => {}} onManage={() => {}} canCreate />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/ }));
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("marks the active profile with aria-current and leaves others unset", async () => {
    render(<ProfileSwitcher profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));

    const activeItem = screen.getByRole("menuitem", { name: /PPR 12-team/ });
    expect(activeItem).toHaveAttribute("aria-current", "true");

    const otherItem = screen.getByRole("menuitem", { name: /Standard Keeper/ });
    expect(otherItem).not.toHaveAttribute("aria-current");
  });

  it("disables + New Profile when canCreate is false", async () => {
    render(<ProfileSwitcher profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    const item = screen.getByRole("menuitem", { name: /\+ New Profile/i });
    expect(item).toHaveAttribute("data-disabled");
  });

  it("calls onManage when 'Manage Profiles…' is chosen", async () => {
    const onManage = vi.fn();
    render(<ProfileSwitcher profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={onManage} canCreate />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    await user.click(screen.getByRole("menuitem", { name: /Manage Profiles/i }));
    expect(onManage).toHaveBeenCalled();
  });
});
