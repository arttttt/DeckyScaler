import { InstalledLibrary, libraryInstalled } from "../api";
import { sharedLoad } from "./sharedLoad";

const useShared = sharedLoad(libraryInstalled, "useInstalledLibrary -> libraryInstalled");

/** The versions games can be patched with; `reload` after the library changes. */
export const useInstalledLibrary = (): { library: InstalledLibrary | null; reload: () => void } => {
  const { value, reload } = useShared();
  return { library: value, reload };
};
