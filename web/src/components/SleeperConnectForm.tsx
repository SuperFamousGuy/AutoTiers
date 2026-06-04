import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  listSleeperLeagues,
  connectSleeper,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { SleeperLeagueSummary, Profile } from "@/api/types";
import { currentSeason } from "@/lib/season";
import { cn } from "@/lib/utils";

interface Props {
  profile: Profile;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

function StepIndicator({ step }: { step: "username" | "league" }) {
  const atLeague = step === "league";
  return (
    <div className="flex items-center gap-1.5 mb-3 text-xs" aria-label="Connection steps">
      <div
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
          atLeague ? "bg-green-500 text-white" : "bg-primary text-primary-foreground",
        )}
      >
        {atLeague ? "✓" : "1"}
      </div>
      <span className={cn("text-xs font-medium", atLeague && "text-green-600")}>
        Find your account
      </span>
      <div className={cn("h-px flex-1", atLeague ? "bg-primary" : "bg-border")} />
      <div
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
          atLeague
            ? "bg-primary text-primary-foreground"
            : "border-2 border-border text-muted-foreground",
        )}
      >
        2
      </div>
      <span className={cn("text-xs", atLeague ? "font-medium" : "text-muted-foreground")}>
        Pick league
      </span>
    </div>
  );
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function SleeperConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
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
          Sleeper{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
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
          aria-label="Disconnect Sleeper"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function SleeperConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [step, setStep] = useState<"username" | "league">("username");
  const [username, setUsername] = useState("");
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [chosenLeague, setChosenLeague] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const linked = profile.linked_league;
  if (linked?.provider === "sleeper") {
    return (
      <SleeperConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleContinue() {
    setError(null);
    setBusy(true);
    try {
      // Check the current and previous seasons. NFL fantasy leagues persist
      // across years and many users carry leagues forward — checking just the
      // current season makes us reject anyone in the offseason or anyone
      // whose league hasn't rolled over yet.
      const seasons = [currentSeason(), currentSeason() - 1];
      const username_trimmed = username.trim();
      let userNotFound = false;
      const settled = await Promise.all(
        seasons.map(async (season) => {
          try {
            return await listSleeperLeagues(profile.id, username_trimmed, season);
          } catch (e) {
            if (e instanceof ApiError && e.status === 404) userNotFound = true;
            return [];
          }
        }),
      );
      if (userNotFound) {
        setError("We couldn't find that Sleeper username.");
        return;
      }
      // Combine and de-dupe by id, preferring the higher-season entry.
      const flat = settled.flat();
      const byId = new Map<string, SleeperLeagueSummary>();
      for (const l of flat) {
        const existing = byId.get(l.id);
        if (!existing || l.season > existing.season) byId.set(l.id, l);
      }
      const result = Array.from(byId.values()).sort((a, b) => b.season - a.season);
      if (result.length === 0) {
        setError(
          `No Sleeper leagues found for "${username_trimmed}" in ${seasons[1]} or ${seasons[0]}.`,
        );
        return;
      }
      setLeagues(result);
      setChosenLeague(result[0].id);
      setStep("league");
    } catch {
      setError("Couldn't reach Sleeper. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const chosen = leagues.find((l) => l.id === chosenLeague);
      const result = await connectSleeper(profile.id, {
        username: username.trim(),
        league_id: chosenLeague,
        season: chosen?.season ?? currentSeason(),
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkWithoutLeague() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectSleeper(profile.id, { username: username.trim() });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // True when handleContinue confirmed the username exists but found zero
  // leagues across both seasons we check. In that state we offer an inline
  // "Link without a league" button instead of stranding the user.
  const noLeaguesFound = error !== null && error.includes("No Sleeper leagues");

  return (
    <div className="space-y-3">
      <StepIndicator step={step} />
      {error && (
        <div className="space-y-2">
          <p className="text-xs text-red-600">{error}</p>
          {noLeaguesFound && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !username.trim()}
              onClick={handleLinkWithoutLeague}
            >
              Link without a league
            </Button>
          )}
        </div>
      )}
      {step === "username" ? (
        <>
          <label className="block text-sm">
            <span>Sleeper Username</span>
            <input
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-label="Sleeper username"
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button size="sm" disabled={busy || !username.trim()} onClick={handleContinue}>
              Continue
            </Button>
          </div>
        </>
      ) : (
        <>
          <label className="block text-sm">
            <span>Select Your League</span>
            <select
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={chosenLeague}
              onChange={(e) => setChosenLeague(e.target.value)}
              aria-label="Select your league"
            >
              {leagues.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.season})
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => setStep("username")}
            >
              ← Wrong username?
            </button>
            <Button size="sm" disabled={busy} onClick={handleConnect}>
              Connect
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
