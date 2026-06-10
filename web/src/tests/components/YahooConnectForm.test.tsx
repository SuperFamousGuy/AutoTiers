import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { YahooConnectForm } from "@/components/YahooConnectForm";
import * as linkedLeagueApi from "@/api/linkedLeague";
import type { Profile, User } from "@/api/types";

const baseProfile: Profile = {
  id: "prof-1",
  name: "Test",
  settings_json: {},
  rules_json: [],
  linked_league: null,
};

const baseUser: User = {
  id: "usr-1",
  email: "test@example.com",
  yahoo_subject: "sub123",
  yahoo_fantasy_connected: true,
  google_subject: null,
  last_active_profile_id: null,
};

describe("YahooConnectForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches and displays league list when fantasy token present and no league linked", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "My League", season: 2024, num_teams: 12 },
    ]);

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("My League (2024)")).toBeInTheDocument();
    });
  });

  it("shows error when league fetch fails", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockRejectedValue(new Error("Network error"));

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/couldn't reach yahoo/i)).toBeInTheDocument();
    });
  });

  it("calls connectYahoo and onLinked when Connect is clicked", async () => {
    const mockLinked = vi.fn();
    const fakeResult = {
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo" as const,
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
      profile: baseProfile,
    };

    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "My League", season: 2024, num_teams: 12 },
    ]);
    vi.spyOn(linkedLeagueApi, "connectYahoo").mockResolvedValue(fakeResult);

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={mockLinked}
        onRefresh={vi.fn()}
      />,
    );

    await waitFor(() => screen.getByText("My League (2024)"));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(linkedLeagueApi.connectYahoo).toHaveBeenCalledWith("prof-1", {
        league_key: "423.l.1",
        season: 2024,
      });
      expect(mockLinked).toHaveBeenCalledWith(fakeResult);
    });
  });

  it("shows connected state when league is linked", async () => {
    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo",
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm
        profile={profile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("Connected!")).toBeInTheDocument();
    expect(screen.getByText("My League")).toBeInTheDocument();
  });

  it("shows reconnect prompt when yahoo_fantasy_connected is false", () => {
    const user: User = { ...baseUser, yahoo_fantasy_connected: false };

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={user}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /connect yahoo fantasy/i })).toBeInTheDocument();
  });

  it("Connect Yahoo Fantasy button sets window.location.href with yahoo_fantasy intent", async () => {
    const user: User = { ...baseUser, yahoo_fantasy_connected: false };
    Object.defineProperty(window, "location", { value: { href: "" }, writable: true });

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={user}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /connect yahoo fantasy/i }));
    expect(window.location.href).toContain("yahoo_fantasy");
  });

  it("Refresh button in connected state calls refreshLink and onRefresh", async () => {
    vi.spyOn(linkedLeagueApi, "refreshLink").mockResolvedValue({} as any);
    const onRefresh = vi.fn().mockResolvedValue(undefined);

    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo",
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm profile={profile} user={baseUser} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => {
      expect(linkedLeagueApi.refreshLink).toHaveBeenCalledWith("prof-1");
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  it("Refresh error shows 'Refresh failed.' message", async () => {
    vi.spyOn(linkedLeagueApi, "refreshLink").mockRejectedValue(new Error("network"));

    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo",
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm profile={profile} user={baseUser} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /refresh/i }));
    await waitFor(() => expect(screen.getByText("Refresh failed.")).toBeInTheDocument());
  });

  it("Disconnect button calls disconnectLink and onRefresh", async () => {
    vi.spyOn(linkedLeagueApi, "disconnectLink").mockResolvedValue(undefined);
    const onRefresh = vi.fn().mockResolvedValue(undefined);

    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo",
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm profile={profile} user={baseUser} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /disconnect yahoo/i }));

    await waitFor(() => {
      expect(linkedLeagueApi.disconnectLink).toHaveBeenCalledWith("prof-1");
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  it("Disconnect error shows 'Disconnect failed.' message", async () => {
    vi.spyOn(linkedLeagueApi, "disconnectLink").mockRejectedValue(new Error("network"));

    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "prof-1",
        provider: "yahoo",
        league_id: null,
        league_metadata_json: null,
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm profile={profile} user={baseUser} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /disconnect yahoo/i }));
    await waitFor(() => expect(screen.getByText("Disconnect failed.")).toBeInTheDocument());
  });

  it("Connect error shows error message", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "My League", season: 2024, num_teams: 12 },
    ]);
    vi.spyOn(linkedLeagueApi, "connectYahoo").mockRejectedValue(new Error("server error"));

    render(
      <YahooConnectForm profile={baseProfile} user={baseUser} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );

    await waitFor(() => screen.getByText("My League (2024)"));
    await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));

    await waitFor(() =>
      expect(screen.getByText("Connect failed. Please try again.")).toBeInTheDocument(),
    );
  });

  it("selecting a different league sends updated league_key on connect", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "League A", season: 2024, num_teams: 12 },
      { league_key: "423.l.2", name: "League B", season: 2023, num_teams: 10 },
    ]);
    const connectSpy = vi.spyOn(linkedLeagueApi, "connectYahoo").mockResolvedValue({} as any);

    render(
      <YahooConnectForm profile={baseProfile} user={baseUser} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );

    await waitFor(() => screen.getByText("League A (2024)"));

    await userEvent.selectOptions(screen.getByRole("combobox"), "423.l.2");
    await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));

    await waitFor(() =>
      expect(connectSpy).toHaveBeenCalledWith("prof-1", { league_key: "423.l.2", season: 2023 }),
    );
  });

  it("shows 'No Yahoo Fantasy NFL leagues found' when fetch returns empty list", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([]);

    render(
      <YahooConnectForm profile={baseProfile} user={baseUser} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByText(/no yahoo fantasy nfl leagues found/i)).toBeInTheDocument(),
    );
  });
});
