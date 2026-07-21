import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2 } from "lucide-react";
import type { LocalProfile } from "@/hooks/useLocalProfiles";

interface ProfileManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profiles: LocalProfile[];
  activeProfileId: string | null;
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
}

/**
 * Rename/delete for localStorage-backed profiles. Replaces the deleted
 * server-backed `ManageProfilesDialog` — same layout and two-click delete
 * pattern, but every write is synchronous (no network round trip, so there's
 * no busy spinner and no "request failed" branch to handle).
 */
export function ProfileManagerDialog({ open, onOpenChange, profiles, activeProfileId, onRename, onDelete }: ProfileManagerDialogProps) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  const trimmedDraft = draftName.trim();
  // A rename to a name already used by a *different* profile is rejected by
  // useLocalProfiles.rename(); surface it inline (and pre-disable Save) rather
  // than letting the throw bubble.
  const isDuplicateDraft = profiles.some((p) => p.id !== editingId && p.name === trimmedDraft);

  function startRename(p: LocalProfile) {
    setEditingId(p.id);
    setDraftName(p.name);
    setRenameError(null);
  }

  function commitRename(id: string) {
    const trimmed = draftName.trim();
    if (!trimmed || isDuplicateDraft) return;
    try {
      onRename(id, trimmed);
    } catch {
      setRenameError("A profile with that name already exists.");
      return;
    }
    setEditingId(null);
    setRenameError(null);
  }

  function commitDelete(id: string) {
    onDelete(id);
    setConfirmDeleteId(null);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setEditingId(null);
          setConfirmDeleteId(null);
          setRenameError(null);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogTitle>Manage Profiles</DialogTitle>
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
                      onChange={(e) => {
                        setDraftName(e.target.value);
                        setRenameError(null);
                      }}
                      className="flex-1"
                      autoFocus
                      aria-label={`Rename ${p.name}`}
                    />
                    <Button
                      size="sm"
                      onClick={() => commitRename(p.id)}
                      disabled={trimmedDraft === "" || isDuplicateDraft}
                    >
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                      Cancel
                    </Button>
                    {(isDuplicateDraft || renameError) && (
                      <p className="w-full text-xs text-destructive" role="alert">
                        A profile with that name already exists.
                      </p>
                    )}
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
                    <Button size="sm" variant="ghost" onClick={() => startRename(p)}>
                      Rename
                    </Button>
                    {confirmDeleteId === p.id ? (
                      <>
                        <Button size="sm" variant="destructive" onClick={() => commitDelete(p.id)}>
                          {p.id === activeProfileId ? "Delete active profile" : "Confirm Delete"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmDeleteId(null)}>
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setConfirmDeleteId(p.id)}
                        aria-label={`delete ${p.name}`}
                      >
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
