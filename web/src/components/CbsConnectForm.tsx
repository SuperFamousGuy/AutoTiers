import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectCbs,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
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

function CbsConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
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
          CBS{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
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
          aria-label="Disconnect CBS"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function CbsConnectForm({ profile, onLinked, onRefresh }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [leagueId, setLeagueId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const linked = profile.linked_league;
  if (linked?.provider === "cbs") {
    return (
      <CbsConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />
    );
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectCbs(profile.id, {
        email: email.trim(),
        password: password.trim(),
        league_id: leagueId.trim(),
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const connectDisabled =
    busy || email.trim() === "" || password.trim() === "" || leagueId.trim() === "";

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}

      <p className="text-xs text-muted-foreground">
        We send your email and password directly to CBS to get a league access token.
        We don't store your password — only the token CBS gives back.
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
          <span>CBS email</span>
          <input
            type="email"
            className="mt-1 block w-full rounded border px-2 py-1 text-sm"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-label="CBS email"
            placeholder="you@example.com"
          />
        </label>

        <label className="block text-sm">
          <span>CBS password</span>
          <input
            type="password"
            className="mt-1 block w-full rounded border px-2 py-1 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-label="CBS password"
            placeholder="••••••••"
          />
        </label>

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
          Find it in your CBS league URL: https://{leagueId || "123456"}.football.cbssports.com/...
        </p>

        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={connectDisabled}>
            Connect
          </Button>
        </div>
      </form>
    </div>
  );
}
