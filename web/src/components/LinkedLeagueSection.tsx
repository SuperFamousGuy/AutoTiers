import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { refreshLink, disconnectLink } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { Profile } from "@/api/types";

interface Props {
  profile: Profile;
  onChanged: () => Promise<void> | void;
}

export function LinkedLeagueSection({ profile, onChanged }: Props) {
  const [activeForm, setActiveForm] = useState<"sleeper" | "espn" | null>(null);
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

  return (
    <section className="space-y-3 border-t pt-4 mt-4">
      {error && <p className="text-xs text-red-600">{error}</p>}
      {linked ? (
        <div className="flex items-center justify-between">
          <span className="text-sm">
            {linked.provider === "sleeper" ? "Sleeper" : "ESPN"} · {linked.league_metadata_json.name}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
              Refresh
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={handleDisconnect}>
              Disconnect
            </Button>
          </div>
        </div>
      ) : activeForm === "sleeper" ? (
        <SleeperConnectForm
          profileId={profile.id}
          onLinked={async () => { setActiveForm(null); await onChanged(); }}
          onCancel={() => setActiveForm(null)}
        />
      ) : activeForm === "espn" ? (
        <EspnConnectForm
          profileId={profile.id}
          onLinked={async () => { setActiveForm(null); await onChanged(); }}
          onCancel={() => setActiveForm(null)}
        />
      ) : (
        <ul className="space-y-2 text-sm">
          <li className="flex items-center justify-between">
            <span>Sleeper</span>
            <Button size="sm" onClick={() => setActiveForm("sleeper")}>Connect Sleeper</Button>
          </li>
          <li className="flex items-center justify-between">
            <span>ESPN</span>
            <Button size="sm" onClick={() => setActiveForm("espn")}>Connect ESPN</Button>
          </li>
          <li className="flex items-center justify-between text-muted-foreground">
            <span>NFL Fantasy</span>
            <span className="text-xs">Coming soon</span>
          </li>
          <li className="flex items-center justify-between text-muted-foreground">
            <span>CBS</span>
            <span className="text-xs">Coming soon</span>
          </li>
        </ul>
      )}
    </section>
  );
}
