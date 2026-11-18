import { useEffect, useSyncExternalStore } from "react";
import { safeAsyncOperation } from "../utils";

/**
 * What the Quick Access panel and the plugin's page both show, loaded once and shared: a change made on the page
 * shows in the panel. `load` asks the backend; `reload` after a change.
 */
export const sharedLoad = <T,>(load: () => Promise<T>, label: string) => {
  let current: T | null = null;
  let requested = false;
  const listeners = new Set<() => void>();

  const reload = (): void => {
    requested = true;
    void safeAsyncOperation(load, label).then((answer) => {
      if (!answer) {
        requested = false; // the next panel or page that opens asks again
        return;
      }
      current = answer;
      listeners.forEach((listener) => listener());
    });
  };

  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };

  return (): { value: T | null; reload: () => void } => {
    const value = useSyncExternalStore(subscribe, () => current);
    useEffect(() => {
      if (!requested) reload();
    }, []);
    return { value, reload };
  };
};
