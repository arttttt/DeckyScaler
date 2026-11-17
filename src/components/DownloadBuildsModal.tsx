import { ButtonItem, DialogBody, DialogHeader, DropdownItem, Field, ModalRoot } from "@decky/ui";
import { useDownloadBuilds } from "../hooks/useDownloadBuilds";
import { VersionRows } from "./VersionRows";

/** Download Proton builds from their releases; the OptiScaler download dialog's sibling. */
export function DownloadBuildsModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { view, onBuild, onCheck, onDownload } = useDownloadBuilds(onChanged);

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Download Proton</DialogHeader>
      <DialogBody>
        <DropdownItem
          label="Build"
          description={view.buildNote ?? undefined}
          disabled={!view.buildEnabled}
          rgOptions={view.buildOptions}
          selectedOption={view.build}
          onChange={(option) => onBuild(option.data)}
        />
        <ButtonItem layout="below" onClick={onCheck} disabled={!view.checkEnabled}>
          {view.checkLabel}
        </ButtonItem>
        {view.message && <Field description={view.message} />}
        <VersionRows rows={view.rows} onAction={onDownload} />
      </DialogBody>
    </ModalRoot>
  );
}
