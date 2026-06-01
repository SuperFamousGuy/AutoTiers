import { useState } from "react";
import { Button } from "@/components/ui/button";
import { refreshLink, disconnectLink } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import { SleeperIcon, EspnIcon, NflFantasyIcon, CbsIcon } from "@/components/BrandIcons";
import type { Profile } from "@/api/types";

interface Props {
  profile: Profile;
  onChanged: () => Promise<void> | void;
  onConnectSleeper: () => void;
  onConnectEspn: () => void;
}

type Provider = "sleeper" | "espn";

export function LinkedLeagueSection({ profile, onChanged, onConnectSleeper, onConnectEspn }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profile.id);
      await onChanged();
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
      await disconnectLink(profile.id);
      await onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  const linked = profile.linked_league;

  function rowActions(provider: Provider, onConnect: () => void) {
    if (linked?.provider !== provider) {
      const label = provider === "sleeper" ? "Connect Sleeper" : "Connect ESPN";
      return (
        <Button size="sm" aria-label={label} onClick={onConnect}>
          Connect
        </Button>
      );
    }
    return (
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <Button size="sm" variant="outline" disabled={busy} onClick={handleDisconnect}>
          Disconnect
        </Button>
      </div>
    );
  }

  function rowLabel(provider: Provider, name: string, Icon: () => JSX.Element) {
    const isLinked = linked?.provider === provider;
    let suffix = "";
    if (isLinked) {
      if (linked?.league_metadata_json) {
        suffix = ` · ${linked.league_metadata_json.name}`;
      } else {
        suffix = " · account linked (no league)";
      }
    }
    return (
      <span className="flex items-center gap-2">
        <Icon />
        {name}{suffix}
      </span>
    );
  }

  return (
    <section className="space-y-3 mt-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <ul className="space-y-3 text-sm">
        <li className="flex items-center justify-between">
          {rowLabel("sleeper", "Sleeper", SleeperIcon)}
          {rowActions("sleeper", onConnectSleeper)}
        </li>
        <li className="flex items-center justify-between">
          {rowLabel("espn", "ESPN", EspnIcon)}
          {rowActions("espn", onConnectEspn)}
        </li>
        <li className="flex items-center justify-between text-muted-foreground">
          <span className="flex items-center gap-2"><NflFantasyIcon />NFL Fantasy</span>
          <span className="text-xs">Coming Soon</span>
        </li>
        <li className="flex items-center justify-between text-muted-foreground">
          <span className="flex items-center gap-2"><CbsIcon />CBS</span>
          <span className="text-xs">Coming Soon</span>
        </li>
      </ul>
    </section>
  );
}
