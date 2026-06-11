import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectEspn,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
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

function EspnConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    setBusy(true);
    try {
      await disconnectLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
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
          ESPN{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
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
          aria-label="Disconnect ESPN"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function EspnConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [leagueId, setLeagueId] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [swid, setSwid] = useState("");
  const [espnS2, setEspnS2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const linked = profile.linked_league;
  if (linked?.provider === "espn") {
    return (
      <EspnConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const trimmedLeague = leagueId.trim();
      const result = await connectEspn(profile.id, {
        league_id: trimmedLeague || undefined,
        season: trimmedLeague ? currentSeason() : undefined,
        swid: isPrivate ? swid.trim() : undefined,
        espn_s2: isPrivate ? espnS2.trim() : undefined,
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // Public: must have leagueId.
  // Private: leagueId OR (both cookies filled) — allows pre-linking with cookies only.
  const connectDisabled =
    busy ||
    (!isPrivate && leagueId.trim() === "") ||
    (isPrivate && leagueId.trim() === "" && (swid.trim() === "" || espnS2.trim() === ""));

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* Public / Private toggle */}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant={isPrivate ? "outline" : "default"}
          aria-label="Public league"
          onClick={() => setIsPrivate(false)}
        >
          Public league
        </Button>
        <Button
          size="sm"
          variant={isPrivate ? "default" : "outline"}
          aria-label="Private league"
          onClick={() => setIsPrivate(true)}
        >
          Private league
        </Button>
      </div>

      {/* League ID */}
      <label className="block text-sm">
        <span>
          League ID{" "}
          {isPrivate && (
            <span className="text-xs text-muted-foreground">(optional if using cookies only)</span>
          )}
        </span>
        <input
          className="mt-1 block w-full rounded border px-2 py-1 text-sm"
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value)}
          aria-label="League ID"
          placeholder="e.g. 336041"
        />
      </label>
      {!isPrivate && (
        <p className="text-xs text-muted-foreground">
          Find it in your ESPN league URL:{" "}
          /fantasy/football/leagues/<strong>{leagueId || "336041"}</strong>
        </p>
      )}

      {/* Private credentials */}
      {isPrivate && (
        <div className="space-y-2 rounded border bg-muted/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium">🍪 Private credentials</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Open fantasy.espn.com, press F12, then navigate to Cookies:
            Chrome uses <strong>Application → Cookies → fantasy.espn.com</strong>,
            Firefox uses <strong>Storage → Cookies → fantasy.espn.com</strong>.
            Copy the values for <code>SWID</code> and <code>espn_s2</code>.
          </p>
          <label className="block text-xs">
            <span>SWID</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={swid}
              onChange={(e) => setSwid(e.target.value)}
              aria-label="SWID"
              placeholder="{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
            />
          </label>
          <label className="block text-xs">
            <span>espn_s2</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={espnS2}
              onChange={(e) => setEspnS2(e.target.value)}
              aria-label="espn_s2"
              placeholder="long opaque string"
            />
          </label>
        </div>
      )}

      <div className="flex justify-end">
        <Button size="sm" disabled={connectDisabled} onClick={handleConnect}>
          Connect
        </Button>
      </div>
    </div>
  );
}
