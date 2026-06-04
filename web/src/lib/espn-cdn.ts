export function playerHeadshotUrl(espnId: string): string {
  return `https://a.espncdn.com/i/headshots/nfl/players/full/${espnId}.png`;
}

const ESPN_SLUG_OVERRIDES: Record<string, string> = {};

export function teamLogoUrl(teamCode: string): string {
  const slug = ESPN_SLUG_OVERRIDES[teamCode] ?? teamCode.toLowerCase();
  return `https://a.espncdn.com/i/teamlogos/nfl/500/${slug}.png`;
}
