import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import { useLocalFavorites } from "@/hooks/useLocalFavorites";
import { searchPlayers, batchPlayers } from "@/api/favorites";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FavoritesDialog({ open, onOpenChange }: Props) {
  const { players, teams, togglePlayer, toggleTeam } = useLocalFavorites();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle>Favorites</DialogTitle>
        <FavoritesPanel
          favoritePlayerIds={players}
          favoriteTeams={teams}
          onTogglePlayer={togglePlayer}
          onToggleTeam={toggleTeam}
          searchPlayers={searchPlayers}
          batchPlayers={batchPlayers}
        />
      </DialogContent>
    </Dialog>
  );
}
