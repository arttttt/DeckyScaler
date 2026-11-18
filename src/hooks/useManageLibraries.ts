import { useRef, useState } from "react";
import { UserLibraries, userLibraryRemoval, userLibraryRemove } from "../api";
import { LibraryRemoveConfirmation, libraryManageView, libraryRemoveConfirmation } from "../presentation/libraries";
import { actionOutcome } from "../presentation/releases";
import { safeAsyncOperation } from "../utils";

/** State and calls behind the dialog that manages the libraries; `reload` brings them again after a removal. */
export const useManageLibraries = (installed: UserLibraries | null, reload: () => void) => {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<{ id: string; label: string; confirmation: LibraryRemoveConfirmation } | null>(null);

  const remove = async (id: string, label: string) => {
    setBusy(id);
    setMessage(null);
    const answer = await safeAsyncOperation(() => userLibraryRemove(id), "ManageLibraries -> remove");
    setBusy(null);
    setMessage(actionOutcome(answer ?? null, `${label} is removed.`));
    reload();
  };

  /** A removal question being asked or shown: a second press meanwhile asks nothing more. */
  const asking = useRef(false);

  const onRemove = async (id: string, label: string) => {
    if (asking.current) return;
    asking.current = true;
    const removal = await safeAsyncOperation(() => userLibraryRemoval(id), "ManageLibraries -> removal");
    setPending({ id, label, confirmation: libraryRemoveConfirmation(label, removal ?? null) });
  };

  const answered = () => {
    asking.current = false;
    setPending(null);
  };

  const onConfirm = () => {
    if (pending?.confirmation.removes) void remove(pending.id, pending.label);
    answered();
  };

  return {
    view: libraryManageView({ installed, busy, message }),
    onRemove: (id: string, label: string) => void onRemove(id, label),
    confirmation: pending?.confirmation ?? null,
    onConfirm,
    onCancel: answered,
  };
};
