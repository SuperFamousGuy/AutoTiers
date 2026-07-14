import { useState } from "react";
import { Button } from "@/components/ui/button";
import { refreshLink } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import { extractApiErrorMessage } from "@/lib/errors";

interface Props {
  profileId: string;
  provider: "sleeper" | "espn" | "yahoo" | "cbs" | "nfl";
  leagueName: string;
  onRefreshed: () => Promise<void> | void;
}

const PROVIDER_LABELS: Record<Props["provider"], string> = {
  sleeper: "Sleeper",
  espn: "ESPN",
  yahoo: "Yahoo",
  cbs: "CBS",
  nfl: "NFL Fantasy",
};

export function LinkedLeagueChip({ profileId, provider, leagueName, onRefreshed }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = PROVIDER_LABELS[provider];

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      try {
        await refreshLink(profileId);
      } catch (e) {
        setError(
          e instanceof ApiError
            ? extractApiErrorMessage(e.message)
            : "Refresh failed. Try again.",
        );
        return;
      }
      // The refresh landed server-side; a refetch failure is a distinct,
      // non-retryable-as-a-refresh condition, so give it its own message.
      try {
        await onRefreshed();
      } catch {
        setError("Refreshed, but the view couldn't update. Reload to see the latest.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between rounded border bg-muted/40 px-3 py-2 text-xs">
        <span>Auto-detected from {label} · {leagueName}</span>
        <Button size="sm" variant="ghost" disabled={busy} onClick={handleRefresh}>
          Refresh
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-600 mt-1">
          {error}
        </p>
      )}
    </div>
  );
}
