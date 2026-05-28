import { useEffect, useRef } from "react";

interface UseAutoSaveArgs<T> {
  activeId: string | null;
  payload: T;
  save: (id: string, payload: T) => Promise<void>;
  debounceMs?: number;
}

export function useAutoSave<T>({ activeId, payload, save, debounceMs = 800 }: UseAutoSaveArgs<T>): void {
  const initialRender = useRef(true);

  useEffect(() => {
    // Don't fire on the first render (when state hydrates from the profile).
    if (initialRender.current) {
      initialRender.current = false;
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
