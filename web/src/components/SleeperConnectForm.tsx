import { useState } from "react";
import { Button } from "@/components/ui/button";
import { listSleeperLeagues, connectSleeper, type LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { SleeperLeagueSummary } from "@/api/types";
import { currentSeason } from "@/lib/season";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
}

export function SleeperConnectForm({ profileId, onLinked, onCancel }: Props) {
  const [step, setStep] = useState<"username" | "league">("username");
  const [username, setUsername] = useState("");
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [chosenLeague, setChosenLeague] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
            const leagues = await listSleeperLeagues(profileId, username_trimmed, season);
            return leagues;
          } catch (e) {
            if (e instanceof ApiError && e.status === 404) {
              userNotFound = true;
            }
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
          `No Sleeper leagues found for "${username_trimmed}" in ${seasons[1]} or ${seasons[0]}. ` +
          `You can still link your account using "Skip — link account only" above; join a league later and re-link to import its settings.`,
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
      const result = await connectSleeper(profileId, {
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
      const result = await connectSleeper(profileId, { username: username.trim() });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
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
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !username.trim()}
              onClick={handleLinkWithoutLeague}
            >
              Skip — link account only
            </Button>
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
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={() => setStep("username")}>Back</Button>
            <Button size="sm" disabled={busy} onClick={handleConnect}>Connect</Button>
          </div>
        </>
      )}
    </div>
  );
}
