import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import type { Profile } from "@/api/types";

const profiles: Profile[] = [
  { id: "p1", name: "PPR 12-team", settings_json: {}, rules_json: {}, linked_league: null },
  { id: "p2", name: "Standard Keeper", settings_json: {}, rules_json: {}, linked_league: null },
  { id: "p3", name: "Dynasty Superflex", settings_json: {}, rules_json: {}, linked_league: null },
];

function _render(overrides: Partial<Parameters<typeof ManageProfilesDialog>[0]> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    profiles,
    activeProfileId: null,
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<ManageProfilesDialog {...props} />);
  return props;
}

describe("ManageProfilesDialog", () => {
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
    await waitFor(() => expect(props.onRename).toHaveBeenCalledWith("p1", "Updated Name"));
  });

  it("keeps Save disabled when the rename input is only whitespace", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "   ");
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(props.onRename).not.toHaveBeenCalled();
  });

  it("trims surrounding whitespace before calling onRename", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "  Updated Name  ");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(props.onRename).toHaveBeenCalledWith("p1", "Updated Name"));
  });

  it("Cancel during rename reverts back to the read-only row", async () => {
    _render();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByDisplayValue("PPR 12-team")).not.toBeInTheDocument();
    expect(screen.getByText("PPR 12-team")).toBeInTheDocument();
  });

  it("delete is two-click: first click reveals 'Confirm delete', second click calls onDelete", async () => {
    const props = _render();
    const user = userEvent.setup();
    // First click — should reveal Confirm delete, NOT call onDelete yet
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    expect(props.onDelete).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: /confirm delete/i });
    expect(confirm).toBeInTheDocument();

    // Second click — should call onDelete with the profile id
    await user.click(confirm);
    await waitFor(() => expect(props.onDelete).toHaveBeenCalledWith("p1"));
  });

  it("shows an inline error if onRename rejects", async () => {
    const onRename = vi.fn().mockRejectedValue(new Error("server error"));
    _render({ onRename });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "Updated Name");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/rename failed/i)).toBeInTheDocument();
  });

  it("marks only the active profile's row with an Active badge and aria-label", () => {
    _render({ activeProfileId: "p2" });
    // The active row is distinguishable to assistive tech.
    expect(screen.getByLabelText("Standard Keeper (active profile)")).toBeInTheDocument();
    // Exactly one Active badge is rendered, and it belongs to the active profile.
    const badges = screen.getAllByText(/^active$/i);
    expect(badges).toHaveLength(1);
    // The other rows are NOT marked active.
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
    // Confirm-button copy names the consequence for the active profile.
    expect(screen.getByRole("button", { name: /delete active profile/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^confirm delete$/i })).not.toBeInTheDocument();
    // A warning line explains the effect on Settings.
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

  it("shows an inline error if onDelete rejects, and clears confirm state", async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error("server error"));
    _render({ onDelete });
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    await user.click(screen.getByRole("button", { name: /confirm delete/i }));
    expect(await screen.findByText(/delete failed/i)).toBeInTheDocument();
    // Confirm-delete button is cleared so user has to re-confirm
    expect(screen.queryByRole("button", { name: /confirm delete/i })).not.toBeInTheDocument();
  });
});
