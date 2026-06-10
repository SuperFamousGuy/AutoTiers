import { describe, it, expect, vi, afterEach } from "vitest";
import { listProfiles, createProfile, updateProfile, deleteProfile, activateProfile } from "@/api/profiles";
import { ApiError } from "@/api/client";

const sample = { id: "p1", name: "x", settings_json: {}, rules_json: {} };

describe("profiles API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("list returns profiles and active_profile_id", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ profiles: [sample], active_profile_id: "p1" }), { status: 200 }),
    );
    const r = await listProfiles();
    expect(r.profiles).toHaveLength(1);
    expect(r.active_profile_id).toBe("p1");
  });

  it("create POSTs profile body", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(sample), { status: 201 }),
    );
    await createProfile({ name: "x", settings_json: {}, rules_json: {} });
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
  });

  it("update PATCHes by id", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(sample), { status: 200 }),
    );
    await updateProfile("p1", { name: "new" });
    expect(String(spy.mock.calls[0][0])).toContain("/api/profiles/p1");
    expect(spy.mock.calls[0][1]?.method).toBe("PATCH");
  });

  it("delete DELETEs by id", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteProfile("p1");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("activate POSTs to /activate", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(null, { status: 204 }));
    await activateProfile("p1");
    expect(String(spy.mock.calls[0][0])).toContain("/api/profiles/p1/activate");
  });

  it("delete throws ApiError on non-2xx (covers _voidFetch error path)", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("forbidden", { status: 403 }),
    );
    await expect(deleteProfile("p1")).rejects.toBeInstanceOf(ApiError);
  });

  it("activate throws ApiError on non-2xx", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("not found", { status: 404 }),
    );
    await expect(activateProfile("p1")).rejects.toBeInstanceOf(ApiError);
  });
});
