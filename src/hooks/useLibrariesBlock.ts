import { useEffect, useState } from "react";
import { LibrarySlot, LibrarySource, UserLibraries, userLibrariesApply, userLibraryChoose, userLibrarySources } from "../api";
import { setAppLaunchOptions } from "../api/steamClient";
import {
  ApplyConfirmation,
  applyConfirmation,
  applyOutcome,
  chooseOutcome,
  launchOptionsToSet,
  librariesBlockView,
} from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";

/** The libraries block on the OptiScaler page: the choice for every game, and applying it to patched games, asked
 *  right after a pick that reaches some. `reload` brings the libraries again after a change. */
export const useLibrariesBlock = (installed: UserLibraries | null, reload: () => void) => {
  const [sources, setSources] = useState<LibrarySource[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [asking, setAsking] = useState<ApplyConfirmation | null>(null);

  useEffect(() => {
    void safeAsyncOperation(userLibrarySources, "LibrariesBlock -> sources").then((answer) => setSources(answer ?? null));
  }, []);

  const onChoose = async (slot: LibrarySlot, value: string) => {
    setBusy(true);
    setMessage(null);
    const answer = await safeAsyncOperation(() => userLibraryChoose("global", slot, value), "LibrariesBlock -> choose");
    setBusy(false);
    setMessage(chooseOutcome(answer ?? null));
    setAsking(applyConfirmation(answer?.to_apply));
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
    view: librariesBlockView({ installed, sources, busy, message }),
    onChoose: (slot: LibrarySlot, value: string) => void onChoose(slot, value),
    onApply: () => void onApply(),
    confirmation: asking,
    onConfirm: () => {
      setAsking(null);
      void onApply();
    },
    onCancel: () => setAsking(null),
  };
};
