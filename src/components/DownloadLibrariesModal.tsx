import { ButtonItem, DialogBody, DialogHeader, DropdownItem, Field, ModalRoot } from "@decky/ui";
import { useDownloadLibraries } from "../hooks/useDownloadLibraries";
import { VersionRows } from "./VersionRows";

/** Download libraries from their projects' releases. The OptiScaler and Proton download dialogs' sibling. */
export function DownloadLibrariesModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { view, onSource, onCheck, onDownload } = useDownloadLibraries(onChanged);

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Download libraries</DialogHeader>
      <DialogBody>
        {view.sourceChoosable ? (
          <DropdownItem
            label="Library"
            disabled={!view.sourceEnabled}
            rgOptions={view.sourceOptions}
            selectedOption={view.source}
            onChange={(option) => onSource(String(option.data))}
          />
        ) : (
          <Field label="Library" description={view.sourceLabel} />
        )}
        <ButtonItem layout="below" onClick={onCheck} disabled={!view.checkEnabled}>
          {view.checkLabel}
        </ButtonItem>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={onDownload} />
      </DialogBody>
    </ModalRoot>
  );
}
