import { useCallback, useEffect, useState } from "react";
import {
  libraryInstalled,
  libraryRemoval,
  libraryReinstall,
  libraryRemove,
} from "../api";
import {
  ManageAction,
  ManageMenuItem,
  ManageState,
  RemoveConfirmation,
  manageDone,
  manageMenu,
  manageView,
  removeConfirmation,
} from "../presentation/library";
import { actionOutcome } from "../presentation/releases";
import { safeAsyncOperation } from "../utils";
import { useDownloadEvents } from "./useDownloadEvents";

const CALLS: Record<ManageAction, (id: string) => Promise<{ status: string; message?: string }>> = {
  reinstall: libraryReinstall,
  remove: libraryRemove,
};

/** State and calls behind the dialog that manages downloaded versions; `onChanged` runs after any change. */
export const useManageVersions = (onChanged: () => void) => {
  const [state, setState] = useState<ManageState>({ library: null, busy: null, download: null, message: null });
  const [pending, setPending] = useState<{ id: string; confirmation: RemoveConfirmation } | null>(null);

  useDownloadEvents("library_download", (id, received, total) =>
    setState((s) => (s.busy?.id === id && s.busy.action === "reinstall" ? { ...s, download: { received, total } } : s)),
  );

  const load = useCallback(() => {
    void safeAsyncOperation(libraryInstalled, "ManageVersions -> libraryInstalled").then((library) => {
      if (library) setState((s) => ({ ...s, library }));
    });
  }, []);

  useEffect(load, [load]);

  const run = async (id: string, action: ManageAction) => {
    setState((s) => ({ ...s, busy: { id, action }, download: null, message: null }));
    const answer = await safeAsyncOperation(() => CALLS[action](id), `ManageVersions -> ${action}`);
    setState((s) => ({ ...s, busy: null, download: null, message: actionOutcome(answer ?? null, manageDone(action, id)) }));
    if (answer?.status === "success") onChanged();
    load();
  };

  /** A menu item picked for a row (`label` the row's): runs, or first asks what the view model says to ask. */
  const onSelect = async (id: string, label: string, item: ManageMenuItem) => {
    if (!item.confirms) return void run(id, item.action);
    const removal = await safeAsyncOperation(() => libraryRemoval(id), "ManageVersions -> libraryRemoval");
    setPending({ id, confirmation: removeConfirmation(label, removal ?? null) });
  };

  const onConfirm = () => {
    if (pending?.confirmation.removes) void run(pending.id, "remove");
    setPending(null);
  };

  return {
    view: manageView(state),
    menuOf: (id: string) => manageMenu(state.library, id),
    onSelect: (id: string, label: string, item: ManageMenuItem) => void onSelect(id, label, item),
    confirmation: pending?.confirmation ?? null,
    onConfirm,
    onCancel: () => setPending(null),
  };
};
