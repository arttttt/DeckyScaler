import { useState } from "react";
import { userLibraryAdd } from "../api";
import { FileSelectionType, pickPath } from "../api/filePicker";
import { addOutcome, pickerStart } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";
import { usePathDefaults } from "./usePathDefaults";

/** What the user picks to add as a library: a zip or a DLL (a file), or a folder. */
export type AddPick = "file" | "folder";

const SELECTION: Record<AddPick, FileSelectionType> = { file: FileSelectionType.FILE, folder: FileSelectionType.FOLDER };

/** Picking a library on the device and adding it; `onChanged` runs after one is added. */
export const useAddLibrary = (onChanged: () => void) => {
  const defaults = usePathDefaults();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const onPick = async (kind: AddPick) => {
    const picked = await pickPath(SELECTION[kind], pickerStart(defaults));
    if (picked.error) setMessage(picked.error);
    if (!picked.path) return;
    const path = picked.path;
    setBusy(true);
    setMessage(null);
    const answer = await safeAsyncOperation(() => userLibraryAdd(path), "AddLibrary -> add");
    setBusy(false);
    setMessage(addOutcome(answer ?? null));
    if (answer?.status === "success") onChanged();
  };

  return { busy, message, onPick: (kind: AddPick) => void onPick(kind) };
};
