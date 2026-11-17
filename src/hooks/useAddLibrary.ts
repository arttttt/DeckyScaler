import { useEffect, useState } from "react";
import { FileSelectionType, openFilePicker } from "@decky/api";
import { getPathDefaults, userLibraryAdd } from "../api";
import { addOutcome, pickerStarts } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";

/** What the user picks to add as a library: a zip or a DLL (a file), or a folder. */
export type AddPick = "file" | "folder";

const SELECTION: Record<AddPick, FileSelectionType> = { file: FileSelectionType.FILE, folder: FileSelectionType.FOLDER };

/** Picking a library on the device and adding it; `onChanged` runs after one is added. */
export const useAddLibrary = (onChanged: () => void) => {
  const [home, setHome] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void safeAsyncOperation(getPathDefaults, "AddLibrary -> getPathDefaults").then((defaults) => setHome(defaults?.home ?? null));
  }, []);

  /** The picker, from the first start folder it opens in. */
  const pick = async (kind: AddPick): Promise<string | null> => {
    for (const start of pickerStarts(home)) {
      try {
        const picked = await openFilePicker(SELECTION[kind], start, true, true, undefined, undefined, true);
        return picked?.path ?? null;
      } catch (err) {
        console.error("AddLibrary -> openFilePicker", err);
      }
    }
    return null;
  };

  const onPick = async (kind: AddPick) => {
    const path = await pick(kind);
    if (!path) return;
    setBusy(true);
    setMessage(null);
    const answer = await safeAsyncOperation(() => userLibraryAdd(path), "AddLibrary -> add");
    setBusy(false);
    setMessage(addOutcome(answer ?? null));
    if (answer?.status === "success") onChanged();
  };

  return { busy, message, onPick: (kind: AddPick) => void onPick(kind) };
};
