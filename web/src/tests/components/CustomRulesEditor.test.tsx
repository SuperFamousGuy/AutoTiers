import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomRulesEditor } from "@/components/CustomRulesEditor";

describe("CustomRulesEditor", () => {
  it("shows valid JSON indicator when input parses", async () => {
    render(<CustomRulesEditor existingNames={new Set()} onAdd={() => {}} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    const validRule = JSON.stringify({
      name: "My Rule",
      conditions: [{ field: "age", operator: ">", value: 30 }],
      effect: { type: "multiplier", value: 0.9 },
    });
    await user.click(textarea);
    await user.paste(validRule);
    expect(await screen.findByText(/valid/i)).toBeInTheDocument();
  });

  it("shows error when JSON is invalid", async () => {
    render(<CustomRulesEditor existingNames={new Set()} onAdd={() => {}} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    await user.click(textarea);
    await user.paste("{not valid json");
    expect(await screen.findByText(/invalid json/i)).toBeInTheDocument();
  });

  it("calls onAdd when 'Add rule' is clicked with valid input", async () => {
    const onAdd = vi.fn();
    render(<CustomRulesEditor existingNames={new Set()} onAdd={onAdd} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    await user.click(textarea);
    await user.paste(JSON.stringify({
      name: "Old Veteran Penalty",
      conditions: [{ field: "age", operator: ">", value: 34 }],
      effect: { type: "multiplier", value: 0.8 },
    }));
    await screen.findByText(/valid/i);
    await user.click(screen.getByRole("button", { name: /add rule/i }));
    expect(onAdd).toHaveBeenCalled();
    const added = onAdd.mock.calls[0][0];
    expect(added.name).toBe("Old Veteran Penalty");
    expect(added.is_builtin).toBe(false);
    expect(added.enabled).toBe(true);
    expect(added.weight).toBe(1.0);
  });

  it("renders custom rules with delete buttons", async () => {
    const onRemove = vi.fn();
    render(
      <CustomRulesEditor
        existingNames={new Set(["My Custom"])}
        onAdd={() => {}}
        onRemove={onRemove}
        customRules={[
          {
            name: "My Custom",
            conditions: [{ field: "age", operator: ">", value: 30 }],
            effect: { type: "multiplier", value: 0.9 },
            enabled: true, weight: 1.0, is_builtin: false, category: "Custom",
          },
        ]}
      />,
    );
    expect(screen.getByText("My Custom")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /remove my custom/i }));
    expect(onRemove).toHaveBeenCalledWith("My Custom");
  });
});
