import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileProfileMenuItems } from "@/components/MobileProfileMenuItems";
import { DropdownMenu, DropdownMenuContent } from "@/components/ui/dropdown-menu";

const profiles = [
  { id: "p1", name: "PPR 12-team", settings: {}, rules: {} },
  { id: "p2", name: "Standard Keeper", settings: {}, rules: {} },
];

// The items rely on a DropdownMenu Root/Content context (radix). Render them
// inside an open menu so the items are mounted, mirroring the hamburger menu.
function renderInMenu(ui: React.ReactNode) {
  return render(
    <DropdownMenu defaultOpen>
      <DropdownMenuContent>{ui}</DropdownMenuContent>
    </DropdownMenu>,
  );
}

describe("MobileProfileMenuItems", () => {
  it("marks the active profile and lists the others", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    expect(screen.getByRole("menuitem", { name: /✓ PPR 12-team/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Standard Keeper/ })).toBeInTheDocument();
  });

  it("calls onSelect with the profile id when a different profile is chosen", async () => {
    const onSelect = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={onSelect} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /Standard Keeper/ }));
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("calls onNew when + New Profile is chosen", async () => {
    const onNew = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={onNew} onManage={() => {}} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /\+ New Profile/i }));
    expect(onNew).toHaveBeenCalled();
  });

  it("calls onManage when Manage Profiles is chosen", async () => {
    const onManage = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={onManage} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /Manage Profiles/i }));
    expect(onManage).toHaveBeenCalled();
  });

  it("disables + New Profile when canCreate is false", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />,
    );
    expect(screen.getByRole("menuitem", { name: /\+ New Profile/i })).toHaveAttribute("data-disabled");
  });

  it("explains why + New Profile is disabled at the profile cap (#855)", () => {
    const capped = Array.from({ length: 5 }, (_, i) => ({ id: `p${i}`, name: `Profile ${i}`, settings: {}, rules: {} }));
    renderInMenu(
      <MobileProfileMenuItems profiles={capped} activeId="p0" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />,
    );
    const item = screen.getByRole("menuitem", { name: /\+ New Profile/i });
    expect(item).toHaveAttribute("data-disabled");
    expect(item).toHaveAccessibleName(/5\/5.*delete one to add another/i);
    expect(item).toHaveAttribute("title", expect.stringMatching(/limit reached/i));
  });

  it("shows no cap copy while below the profile cap (#855)", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    const item = screen.getByRole("menuitem", { name: /\+ New Profile/i });
    expect(item).not.toHaveAttribute("data-disabled");
    expect(item).not.toHaveAttribute("title");
    expect(item.textContent).not.toMatch(/delete one to add another/i);
  });

  it("still offers create/manage when the user has no profiles", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={[]} activeId={null} onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    expect(screen.getByRole("menuitem", { name: /\+ New Profile/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Manage Profiles/i })).toBeInTheDocument();
  });

  it("shows Undo last change and calls onUndo when canUndo is true (#726)", async () => {
    const onUndo = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems
        profiles={profiles}
        activeId="p1"
        onSelect={() => {}}
        onNew={() => {}}
        onManage={() => {}}
        canCreate
        onUndo={onUndo}
        canUndo
      />,
    );
    const undo = screen.getByRole("menuitem", { name: /Undo last change/i });
    expect(undo).toBeInTheDocument();
    await userEvent.setup().click(undo);
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("omits Undo last change entirely when canUndo is false (#726)", () => {
    renderInMenu(
      <MobileProfileMenuItems
        profiles={profiles}
        activeId="p1"
        onSelect={() => {}}
        onNew={() => {}}
        onManage={() => {}}
        canCreate
        onUndo={() => {}}
        canUndo={false}
      />,
    );
    // Absent, not merely disabled.
    expect(screen.queryByRole("menuitem", { name: /Undo last change/i })).toBeNull();
  });

  it("omits Undo last change when canUndo is true but onUndo is missing (#735)", () => {
    renderInMenu(
      <MobileProfileMenuItems
        profiles={profiles}
        activeId="p1"
        onSelect={() => {}}
        onNew={() => {}}
        onManage={() => {}}
        canCreate
        canUndo
      />,
    );
    // No clickable entry that would no-op without a handler.
    expect(screen.queryByRole("menuitem", { name: /Undo last change/i })).toBeNull();
  });
});
