import { DialogBody, DialogHeader, Field, Menu, MenuItem, ModalRoot, showContextMenu } from "@decky/ui";
import { useManageBuilds } from "../hooks/useManageBuilds";
import { PROTON_MENU } from "../presentation/proton";
import { Confirmation } from "./Confirmation";
import { VersionRows } from "./VersionRows";

/** The Proton builds Steam would find: remove one. The OptiScaler manage dialog's sibling. */
export function ManageBuildsModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { view, onRemove, confirmation, onConfirm, onCancel } = useManageBuilds(onChanged);

  const openMenu = (id: string, label: string) =>
    showContextMenu(
      <Menu label={label}>
        {PROTON_MENU.map((item) => (
          <MenuItem key={item.action} tone={item.destructive ? "destructive" : undefined} onSelected={() => onRemove(id)}>
            {item.label}
          </MenuItem>
        ))}
      </Menu>
    );

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Installed Proton builds</DialogHeader>
      <DialogBody>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={openMenu} />
        {view.usage && <Field description={view.usage} />}
      </DialogBody>
      <Confirmation confirmation={confirmation} onConfirm={onConfirm} onCancel={onCancel} />
    </ModalRoot>
  );
}
