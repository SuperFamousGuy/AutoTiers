import type { Profile } from "@/api/types";

type Linked = NonNullable<Profile["linked_league"]>;

const PROVIDER_LABELS: Record<Linked["provider"], string> = {
  sleeper: "Sleeper",
  espn: "ESPN",
  yahoo: "Yahoo",
  cbs: "CBS",
  nfl: "NFL",
};

/**
 * Providers whose import path actually queries keepers / ADP. Yahoo and NFL
 * hard-code keepers=[] / adp_json=None in the backend (yahoo_fantasy.py,
 * nfl.py) — they never attempt detection — so an assertive "No keepers
 * detected" would assert an absence AutoTiers never checked. For those
 * providers we render neutral "not available yet" copy instead of a negative.
 */
const KEEPER_DETECTION_PROVIDERS = new Set<Linked["provider"]>(["sleeper", "espn", "cbs"]);
const ADP_DETECTION_PROVIDERS = new Set<Linked["provider"]>(["sleeper", "espn", "cbs"]);

/**
 * One muted line under the Connected card's league name reporting what the
 * link actually imported: how many keepers were detected and whether the
 * league carried ADP data. It reads straight off the already-present
 * `keepers_json` / `adp_json` on the linked object, so it updates after a
 * Refresh with no extra API call.
 *
 * The zero-keeper case is stated explicitly ("No keepers detected") rather
 * than omitted — a silent absence is indistinguishable from a detection
 * failure, which is exactly the confusion this line exists to resolve — BUT
 * only for providers that actually run keeper/ADP detection. For providers
 * that never query it (Yahoo, NFL), an assertive negative would itself be the
 * confusion, so we state that detection isn't available rather than claiming
 * none was found.
 *
 * Nothing is rendered when no league is linked (account-only link): there is
 * no league to have imported anything, so a "No keepers / No ADP" line would
 * be misleading rather than reassuring.
 */
export function LeagueImportSummary({ linked }: { linked: Linked }) {
  if (!linked.league_id) return null;

  const label = PROVIDER_LABELS[linked.provider];
  const keepersSupported = KEEPER_DETECTION_PROVIDERS.has(linked.provider);
  const adpSupported = ADP_DETECTION_PROVIDERS.has(linked.provider);

  const keeperCount = linked.keepers_json?.length ?? 0;
  const hasAdp = !!linked.adp_json && Object.keys(linked.adp_json).length > 0;

  const keeperText = !keepersSupported
    ? `Keeper detection isn't available for ${label} leagues yet`
    : keeperCount === 0
      ? "No keepers detected"
      : `${keeperCount} keeper${keeperCount === 1 ? "" : "s"} detected`;

  const adpText = !adpSupported
    ? `League ADP isn't available for ${label} leagues yet`
    : hasAdp
      ? "League ADP available"
      : "No ADP data for this league";

  return (
    <p className="text-xs text-muted-foreground">
      {keeperText} · {adpText}
    </p>
  );
}
