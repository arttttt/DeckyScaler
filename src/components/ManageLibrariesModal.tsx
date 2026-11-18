import { DialogBody, DialogHeader, Field, ModalRoot } from "@decky/ui";
import { useManageLibraries } from "../hooks/useManageLibraries";
import { useUserLibraries } from "../hooks/useUserLibraries";
import { Confirmation } from "./Confirmation";
import { VersionRows } from "./VersionRows";

/** The libraries on the device: remove one. The Proton manage dialog's sibling. */
export function ManageLibrariesModal({ closeModal }: { closeModal?: () => void }) {
  const { installed, reload } = useUserLibraries();
  const { view, onRemove, confirmation, onConfirm, onCancel } = useManageLibraries(installed, reload);

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Libraries</DialogHeader>
      <DialogBody>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={onRemove} />
        {view.usage && <Field description={view.usage} />}
      </DialogBody>
      <Confirmation confirmation={confirmation} onConfirm={onConfirm} onCancel={onCancel} />
    </ModalRoot>
  );
}
