import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import { useFavorites } from "@/hooks/useFavorites";
import { searchPlayers, batchPlayers } from "@/api/favorites";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isLoggedIn: boolean;
}

function FavoritesBody({ isLoggedIn, onRetry }: { isLoggedIn: boolean; onRetry: () => void }) {
  const { favorites, loading, error, save: saveFavorites } = useFavorites(isLoggedIn);
  return (
    <FavoritesPanel
      favorites={favorites}
      loading={loading}
      error={error}
      onRetry={onRetry}
      onSave={saveFavorites}
      searchPlayers={searchPlayers}
      batchPlayers={batchPlayers}
    />
  );
}

export function FavoritesDialog({ open, onOpenChange, isLoggedIn }: Props) {
  const [reloadKey, setReloadKey] = useState(0);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle>Favorites</DialogTitle>
        <FavoritesBody
          key={reloadKey}
          isLoggedIn={isLoggedIn}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      </DialogContent>
    </Dialog>
  );
}
