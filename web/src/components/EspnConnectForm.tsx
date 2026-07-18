import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectEspn,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { currentSeason } from "@/lib/season";
import type { Profile } from "@/api/types";
import { LeagueImportSummary } from "@/components/LeagueImportSummary";

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
          ESPN{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
        <LeagueImportSummary linked={linked} />
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
  const { pending: busy, error, run } = useAsyncAction();

  const linked = profile.linked_league;
  if (linked?.provider === "espn") {
    return (
      <EspnConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleConnect() {
    await run(
      async () => {
        const trimmedLeague = leagueId.trim();
        const result = await connectEspn(profile.id, {
          league_id: trimmedLeague || undefined,
          season: trimmedLeague ? currentSeason() : undefined,
          swid: isPrivate ? swid.trim() : undefined,
          espn_s2: isPrivate ? espnS2.trim() : undefined,
        });
        onLinked(result);
      },
      { fallback: "Connect failed. Please try again." },
    );
  }

  // Public: must have leagueId.
  // Private: leagueId OR (both cookies filled) — allows pre-linking with cookies only.
  // In private mode a half cookie pair (exactly one of SWID/espn_s2 filled) is
  // always invalid, even when a leagueId is present — the backend rejects it and
  // it would otherwise round-trip a stale half-credential.
  const halfCookiePair =
    isPrivate && (swid.trim() === "") !== (espnS2.trim() === "");
  const connectDisabled =
    busy ||
    (!isPrivate && leagueId.trim() === "") ||
    (isPrivate && leagueId.trim() === "" && (swid.trim() === "" || espnS2.trim() === "")) ||
    halfCookiePair;

  return (
    <div className="space-y-3">
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}

      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (connectDisabled) return;
          handleConnect();
        }}
      >
        {/* Public / Private toggle — type=button so they never submit the form */}
        <div className="flex gap-2" role="group" aria-label="League visibility">
          <Button
            type="button"
            size="sm"
            variant={isPrivate ? "outline" : "default"}
            aria-label="Public league"
            aria-pressed={!isPrivate}
            onClick={() => setIsPrivate(false)}
          >
            Public league
          </Button>
          <Button
            type="button"
            size="sm"
            variant={isPrivate ? "default" : "outline"}
            aria-label="Private league"
            aria-pressed={isPrivate}
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
            {/*
              SWID and espn_s2 are long opaque cookie strings the user pastes
              out of devtools — not typed secrets. Rendering them as visible
              text (rather than masked type="password") lets the user verify
              they pasted the full value without clipping a brace off {XXXX...}
              or leaving a trailing space. spellCheck/autoComplete are off so
              the browser doesn't squiggle or reformat the opaque value.
              (CbsConnectForm's real password stays type="password".)
            */}
            <label className="block text-xs">
              <span>SWID</span>
              <input
                type="text"
                spellCheck={false}
                autoComplete="off"
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
                type="text"
                spellCheck={false}
                autoComplete="off"
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
          <Button type="submit" size="sm" disabled={connectDisabled}>
            Connect
          </Button>
        </div>
      </form>
    </div>
  );
}
