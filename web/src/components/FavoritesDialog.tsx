import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import { useFavorites } from "@/hooks/useFavorites";
import { searchPlayers } from "@/api/favorites";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isLoggedIn: boolean;
}

export function FavoritesDialog({ open, onOpenChange, isLoggedIn }: Props) {
  const { favorites, save: saveFavorites } = useFavorites(isLoggedIn);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Favorites</DialogTitle>
        <FavoritesPanel
          favorites={favorites}
          onSave={saveFavorites}
          searchPlayers={searchPlayers}
        />
      </DialogContent>
    </Dialog>
  );
}
