import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileManagerDialog } from "@/components/ProfileManagerDialog";
import type { LocalProfile } from "@/hooks/useLocalProfiles";

const profiles: LocalProfile[] = [
  { id: "p1", name: "PPR 12-team", settings: {}, rules: {} },
  { id: "p2", name: "Standard Keeper", settings: {}, rules: {} },
  { id: "p3", name: "Dynasty Superflex", settings: {}, rules: {} },
];

function _render(overrides: Partial<Parameters<typeof ProfileManagerDialog>[0]> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    profiles,
    activeProfileId: null,
    onRename: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  };
  render(<ProfileManagerDialog {...props} />);
  return props;
}

describe("ProfileManagerDialog", () => {
  it("renders all profile names in the list", () => {
    _render();
    expect(screen.getByText("PPR 12-team")).toBeInTheDocument();
    expect(screen.getByText("Standard Keeper")).toBeInTheDocument();
  });

  it("shows empty state when there are no profiles", () => {
    _render({ profiles: [] });
    expect(screen.getByText(/no profiles yet/i)).toBeInTheDocument();
  });

  it("clicking Rename enables inline edit with the current name", async () => {
    _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    expect(input).toBeInTheDocument();
  });

  it("saving inline edit calls onRename with the new name", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "Updated Name");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(props.onRename).toHaveBeenCalledWith("p1", "Updated Name");
  });

  it("keeps Save disabled when the rename input is only whitespace", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "   ");
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("trims surrounding whitespace before calling onRename", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "  Updated Name  ");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(props.onRename).toHaveBeenCalledWith("p1", "Updated Name");
  });

  it("Cancel during rename reverts back to the read-only row", async () => {
    _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByDisplayValue("PPR 12-team")).not.toBeInTheDocument();
    expect(screen.getByText("PPR 12-team")).toBeInTheDocument();
  });

  it("delete is two-click: first click reveals 'Confirm Delete', second click calls onDelete", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    expect(props.onDelete).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: /confirm delete/i });
    expect(confirm).toBeInTheDocument();

    await user.click(confirm);
    expect(props.onDelete).toHaveBeenCalledWith("p1");
  });

  it("marks only the active profile's row with an Active badge and aria-label", () => {
    _render({ activeProfileId: "p2" });
    expect(screen.getByLabelText("Standard Keeper (active profile)")).toBeInTheDocument();
    const badges = screen.getAllByText(/^active$/i);
    expect(badges).toHaveLength(1);
    expect(screen.queryByLabelText("PPR 12-team (active profile)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Dynasty Superflex (active profile)")).not.toBeInTheDocument();
  });

  it("does not render any Active badge when there is no active profile", () => {
    _render({ activeProfileId: null });
    expect(screen.queryByText(/^active$/i)).not.toBeInTheDocument();
  });

  it("uses distinct confirm copy and a warning when deleting the active profile", async () => {
    _render({ activeProfileId: "p2" });
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete Standard Keeper/i));
    expect(screen.getByRole("button", { name: /delete active profile/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^confirm delete$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/clear it from Settings until you pick another/i)).toBeInTheDocument();
  });

  it("uses the generic confirm copy with no warning when deleting a non-active profile", async () => {
    _render({ activeProfileId: "p2" });
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    expect(screen.getByRole("button", { name: /^confirm delete$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete active profile/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/clear it from Settings until you pick another/i)).not.toBeInTheDocument();
  });

  it("Cancel during confirm-delete reverts the row without deleting", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    expect(screen.getByRole("button", { name: /confirm delete/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /confirm delete/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/delete PPR 12-team/i)).toBeInTheDocument();
  });
});
