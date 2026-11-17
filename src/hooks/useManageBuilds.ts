import { useCallback, useEffect, useState } from "react";
import { protonInstalled, protonRemoval, protonRemove } from "../api";
import {
  ProtonManageState,
  ProtonRemoveConfirmation,
  protonManageView,
  protonOutcome,
  protonRemoveConfirmation,
  removeDone,
} from "../presentation/proton";
import { installedWithSteamNames, withSteamNames } from "../api/steamClient";
import { safeAsyncOperation } from "../utils";

/** State and calls behind the dialog that manages installed Proton builds; `onChanged` runs after a removal. */
export const useManageBuilds = (onChanged: () => void) => {
  const [state, setState] = useState<ProtonManageState>({ installed: null, busy: null, message: null });
  const [pending, setPending] = useState<{ id: string; confirmation: ProtonRemoveConfirmation } | null>(null);

  const load = useCallback(() => {
    void safeAsyncOperation(() => protonInstalled(true), "ManageBuilds -> protonInstalled").then((installed) => {
      if (installed) setState((s) => ({ ...s, installed: installedWithSteamNames(installed) }));
    });
  }, []);

  useEffect(load, [load]);

  const remove = async (id: string) => {
    setState((s) => ({ ...s, busy: id, message: null }));
    const answer = await safeAsyncOperation(() => protonRemove(id), "ManageBuilds -> protonRemove");
    setState((s) => ({ ...s, busy: null, message: protonOutcome(answer ?? null, removeDone(id)) }));
    if (answer?.status === "success") onChanged();
    load();
  };

  /** Remove picked for a build: first the warning naming the games whose user chose it. */
  const onRemove = async (id: string) => {
    const removal = await safeAsyncOperation(() => protonRemoval(id), "ManageBuilds -> protonRemoval");
    const named = removal?.status === "success" ? { ...removal, games: withSteamNames(removal.games) } : removal;
    setPending({ id, confirmation: protonRemoveConfirmation(id, named ?? null) });
  };

  const onConfirm = () => {
    if (pending?.confirmation.removes) void remove(pending.id);
    setPending(null);
  };

  return {
    view: protonManageView(state),
    onRemove: (id: string) => void onRemove(id),
    confirmation: pending?.confirmation ?? null,
    onConfirm,
    onCancel: () => setPending(null),
  };
};
