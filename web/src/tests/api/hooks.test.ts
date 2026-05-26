import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { downloadCsv } from "@/api/hooks";
import type { GenerateRequest } from "@/api/types";

const baseRequest: GenerateRequest = {
  scoring_format: "standard",
  league_type: "standard",
  league_size: 12,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weight_prior_year: 0.3,
  weight_espn: 0,
  weight_consensus: 0.7,
  draft_rounds: 15,
  rules: [],
};

describe("downloadCsv", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let appendChild: ReturnType<typeof vi.fn>;
  let removeChild: ReturnType<typeof vi.fn>;
  let click: ReturnType<typeof vi.fn>;
  const originalCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    revokeObjectURL = vi.fn();
    appendChild = vi.fn();
    removeChild = vi.fn();
    click = vi.fn();

    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });

    vi.spyOn(document.body, "appendChild").mockImplementation(appendChild);
    vi.spyOn(document.body, "removeChild").mockImplementation(removeChild);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        return { href: "", download: "", click } as unknown as HTMLAnchorElement;
      }
      return originalCreateElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs the request body, creates a download link, and clicks it", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("col1,col2\nval1,val2", { status: 200 }),
    );

    await downloadCsv(baseRequest);

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/api/generate/csv");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).headers).toEqual({ "Content-Type": "application/json" });
    expect((init as RequestInit).body).toBe(JSON.stringify(baseRequest));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });

  it("throws when the server returns a non-2xx status", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("internal error", { status: 500 }),
    );

    await expect(downloadCsv(baseRequest)).rejects.toThrow(/CSV download failed: 500/);
    expect(click).not.toHaveBeenCalled();
  });
});
