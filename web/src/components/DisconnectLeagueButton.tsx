import { useState } from "react";
import { Button } from "@/components/ui/button";

interface DisconnectLeagueButtonProps {
  /** Provider display name woven into the accessible label, e.g. "Sleeper" → "Disconnect Sleeper". */
  provider: string;
  /** True while a sibling async action (Refresh/Disconnect) is in flight — disables the whole affordance. */
  busy: boolean;
  /** Fires the actual unlink. Only invoked after the user confirms, never on the first click. */
  onDisconnect: () => void | Promise<void>;
}

/**
 * Disconnecting a league drops the linked import — and with it the keepers
 * exclusion and league ADP that Generate relies on — with no undo, yet the
 * button sits right next to Refresh in the same row (#787). A mis-click used to
 * fire disconnectLink() immediately. Gate it behind the same inline
 * Confirm/Cancel affordance the app already uses for its other destructive
 * actions (Reset Draft in TiersPanel #731, profile delete in
 * ManageProfilesDialog): the first click swaps "Disconnect" for a
 * "Confirm Disconnect" / "Cancel" pair, and only the second click unlinks.
 *
 * Extracted into one component so all five *ConnectForm Connected states share a
 * single implementation — identical behaviour and copy — and future providers
 * inherit it for free. The parent still owns the busy flag and the role=alert
 * error line; this only owns the confirm/cancel toggle.
 */
export function DisconnectLeagueButton({ provider, busy, onDisconnect }: DisconnectLeagueButtonProps) {
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <>
        <Button
          size="sm"
          variant="destructive"
          disabled={busy}
          // Land focus on Confirm the moment the pair appears so the destructive
          // action is keyboard-reachable without a Tab hunt, mirroring #731.
          autoFocus
          onClick={async () => {
            // Keep the Confirm/Cancel pair mounted until the unlink actually
            // resolves — don't flip back to a plain, disabled "Disconnect"
            // while the request is in flight (#812). `busy` (owned by the
            // parent) disables both buttons meanwhile. On success the parent
            // unmounts this component (the league is gone), so no success-path
            // reset is needed; on failure it re-renders the Connected state
            // with its role=alert error and we deliberately leave
            // "Confirm Disconnect" armed, so a single click retries rather than
            // forcing the user back through arm-then-confirm.
            try {
              await onDisconnect();
            } catch {
              // The parent surfaces the failure in its role=alert line; the
              // confirm state stays armed for a one-click retry.
            }
          }}
        >
          Confirm Disconnect
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => setConfirming(false)}
        >
          Cancel
        </Button>
      </>
    );
  }

  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      aria-label={`Disconnect ${provider}`}
      onClick={() => setConfirming(true)}
    >
      Disconnect
    </Button>
  );
}
