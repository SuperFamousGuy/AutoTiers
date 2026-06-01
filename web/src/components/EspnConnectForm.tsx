import { useState } from "react";
import { Button } from "@/components/ui/button";
import { connectEspn, type LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import { currentSeason } from "@/lib/season";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
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
      const trimmedLeague = leagueId.trim();
      const result = await connectEspn(profileId, {
        // Send league_id + season only when the user filled in a league.
        // Otherwise we're pre-linking the ESPN account (cookies only) so the
        // backend skips the league fetch and just stores the credentials.
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

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <label className="block text-sm">
        <span>League ID <span className="text-xs text-muted-foreground">(optional)</span></span>
        <input
          className="mt-1 block w-full rounded border px-2 py-1 text-sm"
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value)}
          aria-label="League ID"
          placeholder="Leave blank to link your ESPN account without a league"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isPrivate}
          onChange={(e) => setIsPrivate(e.target.checked)}
          aria-label="Private league"
        />
        <span>Private League</span>
      </label>
      {isPrivate && (
        <>
          <details className="rounded border bg-muted/40 p-2 text-xs open:pb-3">
            <summary className="cursor-pointer select-none font-medium">
              How to find SWID and espn_s2
            </summary>
            <ol className="mt-2 list-decimal space-y-2 pl-4 text-muted-foreground">
              <li>
                Sign in to{" "}
                <a
                  href="https://fantasy.espn.com"
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  fantasy.espn.com
                </a>{" "}
                in another browser tab.
              </li>
              <li>
                Open DevTools — <kbd className="rounded border px-1">F12</kbd> on
                Windows/Linux,{" "}
                <kbd className="rounded border px-1">⌥ ⌘ I</kbd> on macOS — and
                switch to the <strong>Application</strong> tab (Chrome / Edge)
                or <strong>Storage</strong> tab (Firefox).
              </li>
              <li>
                In the left sidebar, expand <strong>Cookies</strong> and click{" "}
                <code className="rounded bg-foreground/10 px-1">
                  https://fantasy.espn.com
                </code>
                .
              </li>
              <li>
                Copy the <strong>Value</strong> column for the row named{" "}
                <code className="rounded bg-foreground/10 px-1">SWID</code> and
                paste it below. Repeat for{" "}
                <code className="rounded bg-foreground/10 px-1">espn_s2</code>.
              </li>
            </ol>
            <p className="mt-2">
              Prefer video?{" "}
              <a
                href="https://www.youtube.com/results?search_query=espn+fantasy+swid+espn_s2+cookies+devtools"
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                Show me how (YouTube)
              </a>
            </p>
          </details>
          <label className="block text-sm">
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
          <label className="block text-sm">
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
        </>
      )}
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button
          size="sm"
          disabled={
            busy ||
            // Need either a league ID or both cookies — otherwise there's
            // nothing for the backend to link.
            (leagueId.trim() === "" &&
              (!isPrivate || swid.trim() === "" || espnS2.trim() === ""))
          }
          onClick={handleConnect}
        >
          Connect
        </Button>
      </div>
    </div>
  );
}
