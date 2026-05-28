import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfilePicker } from "@/components/ProfilePicker";

const profiles = [
  { id: "p1", name: "PPR 12-team", settings_json: {}, rules_json: [] },
  { id: "p2", name: "Standard Keeper", settings_json: {}, rules_json: [] },
];

describe("ProfilePicker", () => {
  it("renders the active profile name in the trigger", () => {
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />);
    expect(screen.getByRole("button", { name: /PPR 12-team/ })).toBeInTheDocument();
  });

  it("calls onSelect when another profile is clicked", async () => {
    const onSelect = vi.fn();
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={onSelect} onNew={() => {}} onManage={() => {}} canCreate />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/ }));
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("disables + New profile when canCreate is false", async () => {
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    const item = screen.getByRole("menuitem", { name: /\+ New profile/ });
    expect(item).toHaveAttribute("data-disabled");
  });
});
