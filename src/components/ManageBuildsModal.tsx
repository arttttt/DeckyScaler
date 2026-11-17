import { DialogBody, DialogHeader, Field, ModalRoot } from "@decky/ui";
import { useManageBuilds } from "../hooks/useManageBuilds";
import { Confirmation } from "./Confirmation";
import { VersionRows } from "./VersionRows";

/** The Proton builds Steam would find: remove one. The OptiScaler manage dialog's sibling. */
export function ManageBuildsModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { view, onRemove, confirmation, onConfirm, onCancel } = useManageBuilds(onChanged);

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Installed Proton builds</DialogHeader>
      <DialogBody>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={onRemove} />
        {view.usage && <Field description={view.usage} />}
      </DialogBody>
      <Confirmation confirmation={confirmation} onConfirm={onConfirm} onCancel={onCancel} />
    </ModalRoot>
  );
}
