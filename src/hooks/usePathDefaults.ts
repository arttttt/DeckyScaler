import { useEffect, useState } from "react";
import { PathDefaults, getPathDefaults } from "../api";
import { safeAsyncOperation } from "../utils";

/** Where the pickers start, as the backend says; null until it answers, or when it can't. */
export const usePathDefaults = (): PathDefaults | null => {
  const [defaults, setDefaults] = useState<PathDefaults | null>(null);

  useEffect(() => {
    let cancelled = false;
    void safeAsyncOperation(getPathDefaults, "getPathDefaults").then((answer) => {
      if (!cancelled) setDefaults(answer ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return defaults;
};
