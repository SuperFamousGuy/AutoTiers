import { useState } from "react";
import { Button } from "@/components/ui/button";
import { refreshLink } from "@/api/linkedLeague";

interface Props {
  profileId: string;
  provider: "sleeper" | "espn" | "yahoo" | "cbs";
  leagueName: string;
  onRefreshed: () => Promise<void> | void;
}

const PROVIDER_LABELS: Record<Props["provider"], string> = {
  sleeper: "Sleeper",
  espn: "ESPN",
  yahoo: "Yahoo",
  cbs: "CBS",
};

export function LinkedLeagueChip({ profileId, provider, leagueName, onRefreshed }: Props) {
  const [busy, setBusy] = useState(false);
  const label = PROVIDER_LABELS[provider];

  async function handleRefresh() {
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefreshed();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-between rounded border bg-muted/40 px-3 py-2 text-xs">
      <span>Auto-detected from {label} · {leagueName}</span>
      <Button size="sm" variant="ghost" disabled={busy} onClick={handleRefresh}>
        Refresh
      </Button>
    </div>
  );
}
