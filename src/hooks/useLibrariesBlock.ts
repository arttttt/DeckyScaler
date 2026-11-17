import { useState } from "react";
import { LibrarySlot, UserLibraries, userLibrariesApply, userLibraryChoose } from "../api";
import { setAppLaunchOptions } from "../api/steamClient";
import { applyOutcome, chooseOutcome, launchOptionsToSet, librariesBlockView } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";

/** The libraries block on the OptiScaler page: the choice for every game, and applying it to patched games.
 *  `reload` brings the libraries again after a change. */
export const useLibrariesBlock = (installed: UserLibraries | null, reload: () => void) => {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const onChoose = async (slot: LibrarySlot, value: string) => {
    setBusy(true);
    setMessage(null);
    const answer = await safeAsyncOperation(() => userLibraryChoose("global", slot, value), "LibrariesBlock -> choose");
    setBusy(false);
    setMessage(chooseOutcome(answer ?? null));
    reload();
  };

  const onApply = async () => {
    setBusy(true);
    setMessage(null);
    const answer = await safeAsyncOperation(userLibrariesApply, "LibrariesBlock -> apply");
    launchOptionsToSet(answer ?? null).forEach(({ appid, options }) => setAppLaunchOptions(appid, options));
    setBusy(false);
    setMessage(applyOutcome(answer ?? null));
    reload();
  };

  return {
    view: librariesBlockView({ installed, busy, message }),
    onChoose: (slot: LibrarySlot, value: string) => void onChoose(slot, value),
    onApply: () => void onApply(),
  };
};
