import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import type { Profile } from "@/api/types";

const profiles: Profile[] = [
  { id: "p1", name: "PPR 12-team", settings_json: {}, rules_json: {}, linked_league: null },
  { id: "p2", name: "Standard Keeper", settings_json: {}, rules_json: {}, linked_league: null },
];

function _render(overrides: Partial<Parameters<typeof ManageProfilesDialog>[0]> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    profiles,
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

  it("Cancel during confirm-delete reverts the row without deleting", async () => {
    const props = _render();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));
    // Confirm-delete state is active
    expect(screen.getByRole("button", { name: /confirm delete/i })).toBeInTheDocument();
    // A keyboard-reachable Cancel backs out without deleting
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /confirm delete/i })).not.toBeInTheDocument();
    // Row is back to normal — the trash affordance is visible again
    expect(screen.getByLabelText(/delete PPR 12-team/i)).toBeInTheDocument();
  });

  it("disables the row's buttons while a rename is in flight and cannot double-submit", async () => {
    let resolveRename: () => void = () => {};
    const onRename = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveRename = resolve; }),
    );
    _render({ onRename });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByDisplayValue("PPR 12-team");
    await user.clear(input);
    await user.type(input, "Updated Name");

    const save = screen.getByRole("button", { name: /^save$/i });
    await user.click(save);
    // In flight: Save and Cancel are disabled, so a rapid second click can't re-fire
    expect(save).toBeDisabled();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeDisabled();
    // A spinner communicates the in-flight state on the active button
    expect(save.querySelector(".animate-spin")).toBeInTheDocument();
    await user.click(save);
    expect(onRename).toHaveBeenCalledTimes(1);

    resolveRename();
    await waitFor(() => expect(screen.queryByDisplayValue("Updated Name")).not.toBeInTheDocument());
  });

  it("disables the row's buttons while a delete is in flight and cannot double-submit", async () => {
    let resolveDelete: () => void = () => {};
    const onDelete = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveDelete = resolve; }),
    );
    _render({ onDelete });
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/delete PPR 12-team/i));

    const confirm = screen.getByRole("button", { name: /confirm delete/i });
    await user.click(confirm);
    // In flight: Confirm Delete and Cancel are disabled, so a rapid second click can't re-fire
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeDisabled();
    // A spinner communicates the in-flight state on the active button
    expect(confirm.querySelector(".animate-spin")).toBeInTheDocument();
    await user.click(confirm);
    expect(onDelete).toHaveBeenCalledTimes(1);

    resolveDelete();
    await waitFor(() => expect(screen.queryByRole("button", { name: /confirm delete/i })).not.toBeInTheDocument());
  });
});
