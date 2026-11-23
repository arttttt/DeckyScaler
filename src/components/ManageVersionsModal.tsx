import { DialogBody, DialogHeader, Field, Menu, MenuItem, ModalRoot, showContextMenu } from "@decky/ui";
import { useManageVersions } from "../hooks/useManageVersions";
import { Confirmation } from "./Confirmation";
import { VersionRows } from "./VersionRows";

/** The OptiScaler versions on the device, and what is left of damaged ones: download one again, remove one. */
export function ManageVersionsModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { view, menuOf, onSelect, confirmation, onConfirm, onCancel } = useManageVersions(onChanged);

  const openMenu = (id: string, label: string) =>
    showContextMenu(
      <Menu label={label}>
        {menuOf(id).map((item) => (
          <MenuItem key={item.action} tone={item.destructive ? "destructive" : undefined} onSelected={() => onSelect(id, label, item)}>
            {item.label}
          </MenuItem>
        ))}
      </Menu>
    );

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Downloaded OptiScaler versions</DialogHeader>
      <DialogBody>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={openMenu} />
        {view.usage && <Field description={view.usage} />}
      </DialogBody>
      <Confirmation confirmation={confirmation} onConfirm={onConfirm} onCancel={onCancel} />
    </ModalRoot>
  );
}
