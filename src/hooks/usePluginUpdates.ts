import { useEffect, useSyncExternalStore } from "react";
import { latestStable, pluginBuild, setDeveloperMode } from "../api";
import { UpdatesCheck, withDeveloperMode } from "../presentation/updates";
import { BACKEND_DID_NOT_ANSWER } from "../presentation/words";
import { safeAsyncOperation } from "../utils";

// One copy for the Quick Access panel and the plugin's page: the release is checked once when either
// first opens, and again by the page's button.
let state: UpdatesCheck = { build: null, checking: false, latest: null };
let started = false;
const listeners = new Set<() => void>();

const set = (next: Partial<UpdatesCheck>): void => {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
};

const loadBuild = async (): Promise<void> => {
  const build = await safeAsyncOperation(pluginBuild, "usePluginUpdates -> pluginBuild");
  if (build) set({ build });
};

const check = async (): Promise<void> => {
  if (state.checking || state.build?.known !== true) return;
  set({ checking: true });
  const latest = await safeAsyncOperation(latestStable, "usePluginUpdates -> latestStable");
  set({ checking: false, latest: latest ?? { status: "error", message: BACKEND_DID_NOT_ANSWER } });
};

const start = (): void => {
  if (started) return;
  started = true;
  void loadBuild().then(check);
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** The running build and the newest release; turning Developer mode on or off. */
export const usePluginUpdates = () => {
  const current = useSyncExternalStore(subscribe, () => state);
  useEffect(start, []);
  return {
    check: current,
    onCheck: () => void check(),
    /** Saves Developer mode and keeps what the backend made of it. Without an answer it reads the build again, to
     *  learn whether the save happened. */
    onDeveloperMode: async (on: boolean): Promise<string | null> => {
      const answer = await safeAsyncOperation(() => setDeveloperMode(on), "usePluginUpdates -> setDeveloperMode");
      if (!answer) {
        await loadBuild();
        return BACKEND_DID_NOT_ANSWER;
      }
      if (answer.status === "error") return answer.message;
      set({ build: withDeveloperMode(state.build, answer.developer_mode) });
      return null;
    },
  };
};
