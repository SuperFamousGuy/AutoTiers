/**
 * Persistent, non-dismissible banner shown when a logged-in user has zero
 * profiles. Without an active profile, autosave is silently disabled — every
 * Settings/Rules edit is discarded with no PATCH ever firing (#606). The
 * banner names that fact and offers a one-click fix.
 *
 * The backend now seeds a default profile on OAuth first-login, so this is a
 * belt-and-suspenders guard for legacy accounts (and any edge case) that
 * still land with no profile.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  /** Create + activate a profile. Reuses App's handleNewProfile. */
  onCreateProfile: () => Promise<void>;
}

export function NoProfileBanner({ onCreateProfile }: Props) {
  const [creating, setCreating] = useState(false);

  async function handleCreate() {
    setCreating(true);
    try {
      await onCreateProfile();
    } catch {
      // Re-enable the button so the user can retry. handleNewProfile surfaces
      // its own errors; here we only need to leave the banner usable.
      setCreating(false);
    }
  }

  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b border-red-300 bg-red-50 px-4 py-2.5 text-red-900 dark:border-red-700/60 dark:bg-red-950/40 dark:text-red-200"
    >
      <div className="min-w-0 flex-1 text-xs">
        You don&apos;t have a profile yet — changes won&apos;t be saved until you create one.
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-xs text-red-900 hover:bg-red-100 hover:text-red-900 dark:text-red-200 dark:hover:bg-red-900/30"
          onClick={handleCreate}
          disabled={creating}
        >
          {creating ? "Creating..." : "Create profile"}
        </Button>
      </div>
    </div>
  );
}
