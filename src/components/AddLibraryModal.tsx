import { ButtonItem, DialogBody, DialogHeader, Field, ModalRoot } from "@decky/ui";
import { useAddLibrary } from "../hooks/useAddLibrary";
import { ADD_HINT } from "../presentation/libraries";

/** Add a library the user brought onto the device: its zip or a DLL, or its folder. */
export function AddLibraryModal({ closeModal, onChanged }: { closeModal?: () => void; onChanged: () => void }) {
  const { busy, message, onPick } = useAddLibrary(onChanged);

  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize={true}>
      <DialogHeader>Add a library</DialogHeader>
      <DialogBody>
        <Field description={ADD_HINT} />
        <ButtonItem layout="below" disabled={busy} onClick={() => onPick("file")}>
          Choose a zip or DLL…
        </ButtonItem>
        <ButtonItem layout="below" disabled={busy} onClick={() => onPick("folder")}>
          Choose a folder…
        </ButtonItem>
        {message && <Field description={message} />}
      </DialogBody>
    </ModalRoot>
  );
}
