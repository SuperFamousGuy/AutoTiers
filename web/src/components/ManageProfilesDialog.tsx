import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2, Loader2 } from "lucide-react";
import type { Profile } from "@/api/types";

interface ManageProfilesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profiles: Profile[];
  activeProfileId: string | null;
  onRename: (id: string, newName: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export function ManageProfilesDialog({ open, onOpenChange, profiles, activeProfileId, onRename, onDelete }: ManageProfilesDialogProps) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function handleRename(id: string) {
    if (busyId) return;
    setError(null);
    setBusyId(id);
    try {
      await onRename(id, draftName.trim());
      setEditingId(null);
    } catch {
      setError("Rename failed. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: string) {
    if (busyId) return;
    setError(null);
    setBusyId(id);
    try {
      await onDelete(id);
      setConfirmDeleteId(null);
    } catch {
      setError("Delete failed. Please try again.");
      setConfirmDeleteId(null);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Manage Profiles</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        {confirmDeleteId !== null && confirmDeleteId === activeProfileId && (
          <p className="text-xs text-muted-foreground mb-2">
            Deleting your active profile will clear it from Settings until you pick another.
          </p>
        )}
        {profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No profiles yet.</p>
        ) : (
          <ul className="space-y-2">
            {profiles.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2">
                {editingId === p.id ? (
                  <>
                    <Input
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      className="flex-1"
                      autoFocus
                    />
                    <Button size="sm" onClick={() => handleRename(p.id)} disabled={draftName.trim() === "" || busyId !== null}>
                      {busyId === p.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingId(null)} disabled={busyId !== null}>Cancel</Button>
                  </>
                ) : (
                  <>
                    <span
                      className="flex-1 flex items-center gap-2 min-w-0"
                      aria-label={p.id === activeProfileId ? `${p.name} (active profile)` : undefined}
                    >
                      <span className="min-w-0 truncate">{p.name}</span>
                      {p.id === activeProfileId && (
                        <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                          Active
                        </span>
                      )}
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => { setEditingId(p.id); setDraftName(p.name); setError(null); }} disabled={busyId !== null}>Rename</Button>
                    {confirmDeleteId === p.id ? (
                      <>
                        <Button size="sm" variant="destructive" onClick={() => handleDelete(p.id)} disabled={busyId !== null}>
                          {busyId === p.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {p.id === activeProfileId ? "Delete active profile" : "Confirm Delete"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmDeleteId(null)} disabled={busyId !== null}>Cancel</Button>
                      </>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => { setConfirmDeleteId(p.id); setError(null); }} disabled={busyId !== null} aria-label={`delete ${p.name}`}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
