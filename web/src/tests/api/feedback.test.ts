import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { sendFeedback } from "@/api/feedback";

const API_URL = "http://localhost:8000";

let lastBody: Record<string, unknown> | null = null;

const server = setupServer(
  http.post(`${API_URL}/api/feedback`, async ({ request }) => {
    lastBody = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ detail: "Thanks for the feedback!" }, { status: 202 });
  }),
);

beforeAll(() => server.listen());
afterEach(() => {
  lastBody = null;
});
afterAll(() => server.close());

describe("sendFeedback", () => {
  it("sends message and category without screenshot fields when no attachment", async () => {
    await sendFeedback("hello", "bug");
    expect(lastBody).toEqual({ message: "hello", category: "bug" });
    expect(lastBody).not.toHaveProperty("screenshot");
  });

  it("defaults the category to idea when omitted", async () => {
    await sendFeedback("no category");
    expect(lastBody).toMatchObject({ message: "no category", category: "idea" });
  });

  it("includes the screenshot fields in the body when an attachment is given", async () => {
    await sendFeedback("with shot", "other", {
      base64: "QUJD",
      name: "shot.png",
      type: "image/png",
    });
    expect(lastBody).toEqual({
      message: "with shot",
      category: "other",
      screenshot: "QUJD",
      screenshot_name: "shot.png",
      screenshot_type: "image/png",
    });
  });

  it("omits screenshot fields when attachment is explicitly null", async () => {
    await sendFeedback("nullshot", "idea", null);
    expect(lastBody).not.toHaveProperty("screenshot");
  });
});
