import { ButtonItem, DialogBody, PanelSection, PanelSectionRow, useParams } from "@decky/ui";
import { openSettingsPage } from "../api/pages";
import { useGameLibraries } from "../hooks/useGameLibraries";
import { useGamePatch } from "../hooks/useGamePatch";
import { useInstalledLibrary } from "../hooks/useInstalledLibrary";
import { usePatchPickers } from "../hooks/usePatchPickers";
import { gamePageTitle } from "../presentation/patching";
import { Confirmation } from "./Confirmation";
import { GamePatchCard } from "./GamePatchCard";
import { LibraryPickers } from "./LibraryPickers";
import { PatchPickers } from "./PatchPickers";

/** A Steam game's page in the plugin: its patch with the version, proxy and libraries to use, and its settings. */
export function GamePage() {
  const { appid } = useParams<{ appid: string }>();
  const { library } = useInstalledLibrary();
  const pickers = usePatchPickers(library);
  const patch = useGamePatch(appid, (status) => pickers.forGame(status).patchWith);
  const picked = pickers.forGame(patch.status);
  const libraries = useGameLibraries(
    appid, patch.status?.name ?? "the game", picked.choice.takesLibraries, patch.status, () => void patch.onPatch(),
  );

  return (
    <DialogBody>
      <PanelSection title={gamePageTitle(patch.status)}>
        <PatchPickers pickers={pickers} picked={picked} />
        <LibraryPickers view={libraries.view} onChoose={libraries.onChoose} />
        <Confirmation confirmation={libraries.confirmation} onConfirm={libraries.onConfirm} onCancel={libraries.onCancel} />
        <GamePatchCard patch={patch} />
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openSettingsPage(appid)}>
            OptiScaler settings
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </DialogBody>
  );
}
