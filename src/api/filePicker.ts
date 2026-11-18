import { FileSelectionType, openFilePicker } from "@decky/api";

export { FileSelectionType };

/** What Decky's picker came back with: the path picked, none when the user cancelled, or why it failed. */
export type Picked = { path: string | null; error: string | null };

/** Decky's rejection when the user closes the picker (decky-loader plugin-loader.tsx, openFilePicker). */
const CANCELLED = "User canceled";

/** Decky's file picker, opened once. A start folder that isn't there shows as an error inside the picker, so its
 *  rejection is the user cancelling, or the picker failing. */
export const pickPath = async (select: FileSelectionType, start: string): Promise<Picked> => {
  try {
    const picked = await openFilePicker(select, start, true, true, undefined, undefined, true);
    return { path: picked?.path ?? null, error: null };
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    return { path: null, error: reason === CANCELLED ? null : reason };
  }
};
