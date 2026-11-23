import { useState } from "react";
import { forgetPatched } from "../api";
import { actionOutcome } from "../presentation/releases";
import { safeAsyncOperation } from "../utils";
import { notify } from "../utils/notify";

/** Forget, for a game on a drive that isn't mounted: drops it from the patched games, then lists them again. */
export const useForgetPatched = (directory: string, onDone: () => void) => {
  const [busy, setBusy] = useState(false);

  const onForget = async () => {
    if (busy) return;
    setBusy(true);
    const answer = await safeAsyncOperation(() => forgetPatched(directory), "Games -> forget");
    setBusy(false);
    notify(actionOutcome(answer ?? null, "Forgotten."));
    onDone();
  };

  return { busy, onForget };
};
