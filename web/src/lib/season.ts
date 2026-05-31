export function currentSeason(): number {
  // NFL season rolls over in March; treat Jan-Feb as the previous season.
  const now = new Date();
  return now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
}
