import { useEffect, useRef } from "react";

interface UseAutoSaveArgs<T> {
  activeId: string | null;
  payload: T;
  save: (id: string, payload: T) => Promise<void>;
  debounceMs?: number;
}

export function useAutoSave<T>({ activeId, payload, save, debounceMs = 800 }: UseAutoSaveArgs<T>): void {
  const initialRender = useRef(true);
  const prevActiveId = useRef(activeId);

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
      save(activeId, payload).catch(() => {
        /* swallow — surfaced via status chip elsewhere */
      });
    }, debounceMs);
    return () => clearTimeout(handle);
  }, [activeId, payload, save, debounceMs]);
}
