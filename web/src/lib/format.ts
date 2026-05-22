export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "unknown";
  const then = new Date(iso);
  const diffMs = now.getTime() - then.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
}

export type Freshness = "fresh" | "stale" | "old" | "unknown";

export function freshnessLevel(iso: string | null, now: Date = new Date()): Freshness {
  if (!iso) return "unknown";
  const ageMs = now.getTime() - new Date(iso).getTime();
  const days = ageMs / 86_400_000;
  if (days < 3) return "fresh";
  if (days <= 7) return "stale";
  return "old";
}
