import { ButtonItem, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { Fragment } from "react";
import { useProtonPage } from "../hooks/useProtonPage";
import { RESTART_TEXT } from "../presentation/proton";
import { DownloadBuildsModal } from "./DownloadBuildsModal";
import { ManageBuildsModal } from "./ManageBuildsModal";

/** Custom Proton builds in Steam: the OptiScaler versions block's sibling, a Steam restart when one is due, and
 *  moving an update's games to the newer build once Steam lists it. */
export function ProtonPage() {
  const { view, reload, onRestart, onMove, onKeep } = useProtonPage();
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
      {view.moves.map((offer) => (
        <Fragment key={offer.move.target}>
          <PanelSectionRow>
            <Field description={offer.text} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!offer.enabled} onClick={() => onMove(offer.move)}>
              {offer.moveLabel}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!offer.enabled} onClick={() => onKeep(offer.move)}>
              {offer.keepLabel}
            </ButtonItem>
          </PanelSectionRow>
        </Fragment>
      ))}
      {view.moveMessage && (
        <PanelSectionRow>
          <Field description={view.moveMessage} />
        </PanelSectionRow>
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
