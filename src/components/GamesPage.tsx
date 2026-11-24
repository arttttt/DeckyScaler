import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { openGamePage } from "../api/pages";
import { useForgetPatched } from "../hooks/useForgetPatched";
import { usePatchedGames } from "../hooks/usePatchedGames";
import { useUnpatch } from "../hooks/useUnpatch";
import type { GameRowView } from "../presentation/games";
import { Confirmation } from "./Confirmation";
import { multiline } from "./MultilineText";

/** A Steam game: its page patches, unpatches and sets it up. */
function SteamGameRow({ row, appid }: { row: GameRowView; appid: string }) {
  return (
    <PanelSectionRow>
      <ButtonItem label={row.title} description={multiline(row.lines)} onClick={() => openGamePage(appid)}>
        {row.action.label}
      </ButtonItem>
    </PanelSectionRow>
  );
}

/** A directory patched by path: it has no game page, so it is unpatched from its row. */
function DirectoryRow({ row, directory, onChanged }: { row: GameRowView; directory: string; onChanged: () => void }) {
  const unpatch = useUnpatch({ kind: "directory", path: directory }, onChanged);
  return (
    <PanelSectionRow>
      <ButtonItem label={row.title} description={multiline(row.lines)} disabled={unpatch.busy} onClick={unpatch.onUnpatch}>
        {row.action.label}
      </ButtonItem>
      <Confirmation confirmation={unpatch.confirmation} onConfirm={unpatch.onConfirm} onCancel={unpatch.onCancel} />
    </PanelSectionRow>
  );
}

/** A game on a drive that isn't mounted: its patch can't be read, so it can only be forgotten. */
function AwayRow({ row, directory, onChanged }: { row: GameRowView; directory: string; onChanged: () => void }) {
  const forget = useForgetPatched(directory, onChanged);
  return (
    <PanelSectionRow>
      <ButtonItem label={row.title} description={multiline(row.lines)} disabled={forget.busy} onClick={forget.onForget}>
        {row.action.label}
      </ButtonItem>
    </PanelSectionRow>
  );
}

const GameRow = ({ row, onChanged }: { row: GameRowView; onChanged: () => void }) => {
  switch (row.action.kind) {
    case "open":
      return <SteamGameRow row={row} appid={row.action.appid} />;
    case "unpatch":
      return <DirectoryRow row={row} directory={row.action.directory} onChanged={onChanged} />;
    case "forget":
      return <AwayRow row={row} directory={row.action.directory} onChanged={onChanged} />;
  }
};

/** Every game the plugin patched: a Steam game opens its page, a directory is unpatched in place, a game on a drive
 *  that isn't mounted is forgotten. */
export function GamesPage() {
  const { view, reload } = usePatchedGames();
  return (
    <PanelSection>
      {view.kind === "message" ? (
        <PanelSectionRow>
          <Field label={view.message} />
        </PanelSectionRow>
      ) : (
        view.rows.map((row) => <GameRow key={row.key} row={row} onChanged={() => void reload()} />)
      )}
    </PanelSection>
  );
}
