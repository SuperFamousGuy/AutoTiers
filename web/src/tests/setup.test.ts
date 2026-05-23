import { describe, it, expect } from "vitest";
import { apiFetch } from "@/api/client";
import type { Rule } from "@/api/types";

describe("MSW setup", () => {
  it("intercepts API calls and returns fixture data", async () => {
    const rules = await apiFetch<Rule[]>("/api/rules");
    expect(rules).toHaveLength(3);
    expect(rules[0].name).toBe("Over the Hill");
  });
});
