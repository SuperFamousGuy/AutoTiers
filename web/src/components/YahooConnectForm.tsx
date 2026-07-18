import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  listYahooLeagues,
  connectYahoo,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
  type YahooLeagueSummary,
} from "@/api/linkedLeague";
import { yahooAuthorizeUrl } from "@/api/auth";
import { DisconnectLeagueButton } from "@/components/DisconnectLeagueButton";
import { useAsyncAction, toActionErrorMessage } from "@/hooks/useAsyncAction";
import type { Profile, User } from "@/api/types";
import { LeagueImportSummary } from "@/components/LeagueImportSummary";

interface Props {
  profile: Profile;
  user: User;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function YahooConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
  const { pending: busy, error, run } = useAsyncAction();

  async function handleRefresh() {
    await run(
      async () => {
        await refreshLink(profileId);
        await onRefresh();
      },
      { fallback: "Refresh failed." },
    );
  }

  async function handleDisconnect() {
    await run(
      async () => {
        await disconnectLink(profileId);
        await onRefresh();
      },
      { fallback: "Disconnect failed." },
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
      <div className="rounded-lg border-2 border-green-500 bg-green-50/50 dark:bg-green-900/30 p-3">
        <div className="mb-1 flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500">
            <span className="text-[10px] font-bold text-white">✓</span>
          </div>
          <span className="text-sm font-bold text-green-700 dark:text-green-400">Connected!</span>
        </div>
        <p className="text-sm font-medium">
          {linked.league_metadata_json?.name ?? "Account linked (no league)"}
        </p>
        <p className="text-xs text-muted-foreground">
          Yahoo{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
        <LeagueImportSummary linked={linked} />
      </div>
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <DisconnectLeagueButton provider="Yahoo" busy={busy} onDisconnect={handleDisconnect} />
      </div>
    </div>
  );
}

export function YahooConnectForm({ profile, user, onLinked, onRefresh }: Props) {
  const linked = profile.linked_league;
  const showPicker = !linked && user.yahoo_fantasy_connected;

  // All hooks unconditionally before any early return.
  const [leagues, setLeagues] = useState<YahooLeagueSummary[]>([]);
  const [chosenKey, setChosenKey] = useState("");
  const [loading, setLoading] = useState(false);
  const { pending: busy, error, run, setError } = useAsyncAction();

  useEffect(() => {
    if (!showPicker) return;
    setLoading(true);
    listYahooLeagues(profile.id)
      .then((data) => {
        setLeagues(data);
        if (data.length > 0) setChosenKey(data[0].league_key);
      })
      .catch((e) => setError(toActionErrorMessage(e, "Couldn't reach Yahoo. Please try again.")))
      .finally(() => setLoading(false));
  }, [profile.id, showPicker, setError]);

  if (linked?.provider === "yahoo") {
    return <YahooConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />;
  }

  if (!user.yahoo_subject) {
    return (
      <div className="space-y-3 py-2">
        <p className="text-sm text-muted-foreground">
          Connect via Yahoo OAuth. We'll find your Yahoo Fantasy leagues automatically after you
          authorize.
        </p>
        <Button
          className="w-full"
          onClick={() => {
            window.location.href = `${yahooAuthorizeUrl()}?intent=link`;
          }}
        >
          Continue with Yahoo
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          You'll be redirected to Yahoo, then brought back here.
        </p>
      </div>
    );
  }

  if (!user.yahoo_fantasy_connected) {
    return (
      <div className="space-y-3 py-2">
        <p className="text-sm text-muted-foreground">
          Your Yahoo account is linked for sign-in{user.email ? ` as ${user.email}` : ""}. To import
          league data, authorize Fantasy Sports access.
        </p>
        <Button
          className="w-full"
          aria-label="Connect Yahoo Fantasy"
          onClick={() => {
            window.location.href = `${yahooAuthorizeUrl()}?intent=yahoo_fantasy`;
          }}
        >
          Connect Yahoo Fantasy
        </Button>
      </div>
    );
  }

  async function handleConnect() {
    await run(
      async () => {
        const chosen = leagues.find((l) => l.league_key === chosenKey);
        const result = await connectYahoo(profile.id, {
          league_key: chosenKey,
          season: chosen?.season ?? new Date().getFullYear(),
        });
        onLinked(result);
      },
      { fallback: "Connect failed. Please try again." },
    );
  }

  if (loading) {
    return (
      <div className="py-6 text-center">
        <span role="status" className="text-xs text-muted-foreground">
          Loading leagues…
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Account-link status, stated independently of league-link status. The tab
          strip's green dot only lights once a league is chosen (see
          LinkedAccountsDialog), so surface the OAuth-linked state here. */}
      <p className="text-xs text-muted-foreground">
        Yahoo account linked{user.email ? ` as ${user.email}` : ""}
        {leagues.length === 0 ? "." : " — choose a league below."}
      </p>
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
      {leagues.length === 0 ? (
        // Only claim "no leagues" when the request actually succeeded and came
        // back empty. On error the message above already explains the failure,
        // so suppress this to avoid implying the lookup returned zero leagues.
        !error && (
          <p className="text-sm text-muted-foreground">
            No Yahoo Fantasy NFL leagues found for your account.
          </p>
        )
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (busy || !chosenKey) return;
            handleConnect();
          }}
        >
          <label className="block text-sm">
            <span>Select Your League</span>
            <select
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={chosenKey}
              onChange={(e) => setChosenKey(e.target.value)}
              aria-label="Select your league"
            >
              {leagues.map((l) => (
                <option key={l.league_key} value={l.league_key}>
                  {l.name} ({l.season})
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={busy || !chosenKey}>
              Connect
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
