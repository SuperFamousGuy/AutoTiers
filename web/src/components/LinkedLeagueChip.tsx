import { Button } from "@/components/ui/button";
import { refreshLink } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import { extractApiErrorMessage } from "@/lib/errors";
import { useAsyncAction } from "@/hooks/useAsyncAction";

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
  const { pending: busy, error, run, setError } = useAsyncAction();
  const label = PROVIDER_LABELS[provider];

  async function handleRefresh() {
    // `run` owns the busy flag and clears the prior error; the two phases below
    // set their own messages and never throw out of it, so its extract-or-
    // fallback mapping stays out of the way.
    await run(async () => {
      try {
        await refreshLink(profileId);
      } catch (e) {
        // `extractApiErrorMessage` can come back empty (e.g. an empty response
        // body), which would blank the alert and recreate the silent failure —
        // fall back to the generic line whenever it does.
        const message = e instanceof ApiError ? extractApiErrorMessage(e.message) : "";
        setError(message || "Refresh failed. Try again.");
        return;
      }
      // The refresh landed server-side; a refetch failure is a distinct,
      // non-retryable-as-a-refresh condition, so give it its own message.
      try {
        await onRefreshed();
      } catch {
        setError("Refreshed, but the view couldn't update. Reload to see the latest.");
      }
    });
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
