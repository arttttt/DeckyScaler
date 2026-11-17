import { DropdownItem, Field, PanelSectionRow } from "@decky/ui";
import type { LibrarySlot } from "../api";
import type { GameLibraryPickers } from "../presentation/libraries";

/** A game's own choice of the user's libraries, per slot, under its version and proxy. */
export function LibraryPickers({ view, onChoose }: { view: GameLibraryPickers; onChoose: (slot: LibrarySlot, picked: string) => void }) {
  return (
    <>
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
      {view.note && (
        <PanelSectionRow>
          <Field description={view.note} />
        </PanelSectionRow>
      )}
    </>
  );
}
