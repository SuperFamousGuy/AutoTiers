import { useState } from "react";
import { Button } from "@/components/ui/button";
import { listSleeperLeagues, connectSleeper, type LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { SleeperLeagueSummary } from "@/api/types";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
}

function currentSeason(): number {
  // NFL season rolls over in March; treat Jan-Feb as the previous season.
  const now = new Date();
  return now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
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
      const result = await listSleeperLeagues(profileId, username.trim(), currentSeason());
      if (result.length === 0) {
        setError("No Sleeper leagues found for that username this season.");
        return;
      }
      setLeagues(result);
      setChosenLeague(result[0].id);
      setStep("league");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("We couldn't find that Sleeper username.");
      } else {
        setError("Couldn't reach Sleeper. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectSleeper(profileId, {
        username: username.trim(),
        league_id: chosenLeague,
        season: currentSeason(),
      });
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
                <option key={l.id} value={l.id}>{l.name}</option>
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
