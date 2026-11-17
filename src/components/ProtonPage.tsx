import { ButtonItem, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { useProtonPage } from "../hooks/useProtonPage";
import { RESTART_TEXT } from "../presentation/proton";
import { DownloadBuildsModal } from "./DownloadBuildsModal";
import { ManageBuildsModal } from "./ManageBuildsModal";

/** Custom Proton builds in Steam: the OptiScaler versions block's sibling, and a Steam restart when one is due. */
export function ProtonPage() {
  const { view, reload, onRestart } = useProtonPage();
  return (
    <PanelSection title="Proton builds">
      {view.restart && (
        <>
          <PanelSectionRow>
            <Field description={RESTART_TEXT} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={onRestart}>
              Restart Steam
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <Field description={view.summary} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={!view.dialogsEnabled}
          onClick={() => showModal(<DownloadBuildsModal onChanged={reload} />)}
        >
          Download builds…
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={!view.dialogsEnabled}
          onClick={() => showModal(<ManageBuildsModal onChanged={reload} />)}
        >
          Manage installed…
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field description={view.hint} />
      </PanelSectionRow>
    </PanelSection>
  );
}
