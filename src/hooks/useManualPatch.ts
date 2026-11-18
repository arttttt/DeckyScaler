import { useCallback, useState } from "react";
import { runManualPatch } from "../api";
import { FileSelectionType, pickPath } from "../api/filePicker";
import { ManualPatchResult, manualPatchView, pickerStart } from "../presentation/manualPatch";
import { usePathDefaults } from "./usePathDefaults";
import { useUnpatch } from "./useUnpatch";

const errorText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

/** Patching a directory picked by hand: picking it, and patching and unpatching it. */
export const useManualPatch = ({ ready, dllName, patchWith }: { ready: boolean; dllName: string; patchWith: string }) => {
  const defaults = usePathDefaults();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [patching, setPatching] = useState(false);
  const [result, setResult] = useState<ManualPatchResult | null>(null);

  const onPick = useCallback(async () => {
    const picked = await pickPath(FileSelectionType.FOLDER, pickerStart(selectedPath, defaults));
    setPickerError(picked.error);
    if (!picked.path) return;
    setSelectedPath(picked.path);
    setResult(null);
  }, [defaults, selectedPath]);

  const unpatch = useUnpatch(selectedPath ? { kind: "directory", path: selectedPath } : null, () => setResult(null));

  const onPatch = useCallback(async () => {
    if (!selectedPath) return;
    setPatching(true);
    setResult(null);
    try {
      setResult((await runManualPatch(selectedPath, dllName, patchWith)) ?? { status: "error", message: "No response from backend." });
    } catch (err) {
      setResult({ status: "error", message: errorText(err) });
    } finally {
      setPatching(false);
    }
  }, [selectedPath, dllName, patchWith]);

  const view = manualPatchView({ ready, busy: patching ? "patch" : unpatch.busy ? "unpatch" : null, result });
  return { view, selectedPath, pickerError, onPick, onPatch, unpatch };
};
