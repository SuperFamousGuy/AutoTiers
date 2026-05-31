import { useState } from "react";
import { Button } from "@/components/ui/button";
import { connectEspn, type LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
}

function currentSeason(): number {
  const now = new Date();
  return now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
}

export function EspnConnectForm({ profileId, onLinked, onCancel }: Props) {
  const [leagueId, setLeagueId] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [swid, setSwid] = useState("");
  const [espnS2, setEspnS2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectEspn(profileId, {
        league_id: leagueId.trim(),
        season: currentSeason(),
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

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <label className="block text-sm">
        <span>League ID</span>
        <input
          className="mt-1 block w-full rounded border px-2 py-1 text-sm"
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value)}
          aria-label="League ID"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isPrivate}
          onChange={(e) => setIsPrivate(e.target.checked)}
          aria-label="Private league"
        />
        <span>Private league</span>
      </label>
      {isPrivate && (
        <>
          <p className="text-xs text-muted-foreground">
            Find these on fantasy.espn.com → DevTools (F12) → Application → Cookies.
          </p>
          <label className="block text-sm">
            <span>SWID</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={swid}
              onChange={(e) => setSwid(e.target.value)}
              aria-label="SWID"
            />
          </label>
          <label className="block text-sm">
            <span>espn_s2</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={espnS2}
              onChange={(e) => setEspnS2(e.target.value)}
              aria-label="espn_s2"
            />
          </label>
        </>
      )}
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" disabled={busy || !leagueId.trim()} onClick={handleConnect}>
          Connect
        </Button>
      </div>
    </div>
  );
}
