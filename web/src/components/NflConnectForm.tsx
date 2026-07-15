import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectNfl,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { currentSeason } from "@/lib/season";
import type { Profile } from "@/api/types";

interface Props {
  profile: Profile;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function NflConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
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
      {error && <p className="text-xs text-red-600">{error}</p>}
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
          NFL Fantasy{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
      </div>
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          aria-label="Disconnect NFL"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function NflConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [leagueId, setLeagueId] = useState("");
  const [season, setSeason] = useState(String(currentSeason()));
  const { pending: busy, error, run } = useAsyncAction();

  const linked = profile.linked_league;
  if (linked?.provider === "nfl") {
    return (
      <NflConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  const seasonNum = Number(season);
  const seasonValid = /^\d{4}$/.test(season.trim()) && seasonNum >= 1990 && seasonNum <= 2100;

  async function handleConnect() {
    await run(
      async () => {
        const result = await connectNfl(profile.id, {
          league_id: leagueId.trim(),
          season: seasonNum,
        });
        onLinked(result);
      },
      { fallback: "Connect failed. Please try again." },
    );
  }

  const connectDisabled = busy || leagueId.trim() === "" || !seasonValid;

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}

      <p className="text-xs text-muted-foreground">
        We read your NFL.com league's public info — its name and size. No NFL.com login needed.
      </p>

      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (connectDisabled) return;
          handleConnect();
        }}
      >
        <label className="block text-sm">
          <span>League ID</span>
          <input
            className="mt-1 block w-full rounded border px-2 py-1 text-sm"
            value={leagueId}
            onChange={(e) => setLeagueId(e.target.value)}
            aria-label="League ID"
            placeholder="e.g. 123456"
          />
        </label>
        <p className="text-xs text-muted-foreground">
          Find it in your NFL.com league URL: https://fantasy.nfl.com/league/{leagueId || "123456"}
        </p>

        <label className="block text-sm">
          <span>Season</span>
          <input
            type="number"
            className="mt-1 block w-full rounded border px-2 py-1 text-sm"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            aria-label="Season"
            placeholder="2024"
          />
        </label>

        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={connectDisabled} aria-label="Connect NFL">
            Connect
          </Button>
        </div>
      </form>
    </div>
  );
}
