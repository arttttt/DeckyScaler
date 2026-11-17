import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { useLibrariesBlock } from "../hooks/useLibrariesBlock";
import { useUserLibraries } from "../hooks/useUserLibraries";
import { AddLibraryModal } from "./AddLibraryModal";
import { DownloadLibrariesModal } from "./DownloadLibrariesModal";
import { ManageLibrariesModal } from "./ManageLibrariesModal";

/** The user's libraries on the OptiScaler page: the choice for every game, and the dialogs that bring and manage them. */
export function LibrariesSection() {
  const { installed, reload } = useUserLibraries();
  const { view, onChoose, onApply } = useLibrariesBlock(installed, reload);

  return (
    <PanelSection title="Libraries">
      {view.apply && (
        <>
          <PanelSectionRow>
            <Field description={view.apply.text} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!view.apply.enabled} onClick={onApply}>
              {view.apply.label}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {view.message && (
        <PanelSectionRow>
          <Field description={view.message} />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <Field description={view.summary} />
      </PanelSectionRow>
      {view.pickers.map((picker) => (
        <PanelSectionRow key={picker.slot}>
          <DropdownItem
            layout="below"
            label={picker.label}
            description={picker.hint ?? undefined}
            menuLabel={picker.label}
            disabled={!picker.enabled}
            rgOptions={picker.options}
            selectedOption={picker.selected}
            onChange={(option) => onChoose(picker.slot, String(option.data))}
          />
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => showModal(<DownloadLibrariesModal onChanged={reload} />)}>
          Download libraries…
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => showModal(<AddLibraryModal onChanged={reload} />)}>
          Add from file…
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => showModal(<ManageLibrariesModal />)}>
          Manage libraries…
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
