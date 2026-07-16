import { useEffect, useRef } from "react";
import { createSingleFlight, type SerializedWrite } from "@/lib/singleFlight";

interface UseAutoSaveArgs<T> {
  activeId: string | null;
  payload: T;
  save: (id: string, payload: T) => Promise<void>;
  debounceMs?: number;
}

export function useAutoSave<T>({ activeId, payload, save, debounceMs = 800 }: UseAutoSaveArgs<T>): void {
  const initialRender = useRef(true);
  const prevActiveId = useRef(activeId);

  // Always call the latest `save` closure (App recreates it every render to
  // capture live state) without re-creating the single-flight queue.
  const saveRef = useRef(save);
  saveRef.current = save;

  // Serialize writes per profile id. The debounce below only stops a second
  // *timer* from arming; it does not stop a second `save()` from starting while
  // a prior PATCH is still in flight. Two overlapping full-replace PATCHes race
  // at the DB and whichever response lands last wins — a silent lost update.
  // Single-flighting (trailing-coalesce) makes the server see one write at a
  // time per id, in causal order.
  const runSave = useRef<SerializedWrite<T> | undefined>(undefined);
  if (!runSave.current) {
    runSave.current = createSingleFlight<T>((id, p) => saveRef.current(id, p));
  }

  useEffect(() => {
    // Don't fire on the first render (when state hydrates from the profile).
    if (initialRender.current) {
      initialRender.current = false;
      prevActiveId.current = activeId;
      return;
    }
    // Don't fire when the active profile just changed. On the render right after
    // a switch, `payload` still holds the previous profile's values (it's only
    // replaced by a separate hydration effect). Arming a timer here would pair
    // the new id with a stale payload and could overwrite the just-switched
    // profile's server-side settings. Resume autosaving only once `payload`
    // changes while `activeId` stays the same.
    if (prevActiveId.current !== activeId) {
      prevActiveId.current = activeId;
      return;
    }
    if (!activeId) return;

    const handle = setTimeout(() => {
      runSave.current!(activeId, payload).catch(() => {
        /* swallow — surfaced via status chip elsewhere */
      });
    }, debounceMs);
    return () => clearTimeout(handle);
    // `save` is intentionally omitted: the effect calls it via `saveRef.current`,
    // and App recreates `save` every render. Including it would re-run this effect
    // (resetting the debounce timer) on unrelated re-renders and could delay
    // autosave indefinitely.
  }, [activeId, payload, debounceMs]);
}
