import type { Profile } from "@/api/types";

type Linked = NonNullable<Profile["linked_league"]>;

/**
 * One muted line under the Connected card's league name reporting what the
 * link actually imported: how many keepers were detected and whether the
 * league carried ADP data. It reads straight off the already-present
 * `keepers_json` / `adp_json` on the linked object, so it updates after a
 * Refresh with no extra API call.
 *
 * The zero-keeper case is stated explicitly ("No keepers detected") rather
 * than omitted — a silent absence is indistinguishable from a detection
 * failure, which is exactly the confusion this line exists to resolve.
 *
 * Nothing is rendered when no league is linked (account-only link): there is
 * no league to have imported anything, so a "No keepers / No ADP" line would
 * be misleading rather than reassuring.
 */
export function LeagueImportSummary({ linked }: { linked: Linked }) {
  if (!linked.league_id) return null;

  const keeperCount = linked.keepers_json?.length ?? 0;
  const hasAdp = !!linked.adp_json && Object.keys(linked.adp_json).length > 0;

  const keeperText =
    keeperCount === 0
      ? "No keepers detected"
      : `${keeperCount} keeper${keeperCount === 1 ? "" : "s"} detected`;
  const adpText = hasAdp ? "League ADP available" : "No ADP data for this league";

  return (
    <p className="text-xs text-muted-foreground">
      {keeperText} · {adpText}
    </p>
  );
}
