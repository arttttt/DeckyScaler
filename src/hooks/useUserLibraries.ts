import { UserLibraries, userLibrariesInstalled } from "../api";
import { sharedLoad } from "./sharedLoad";

const useShared = sharedLoad(userLibrariesInstalled, "useUserLibraries -> userLibrariesInstalled");

/** The user's libraries and the choice for every game; `reload` after either changes. */
export const useUserLibraries = (): { installed: UserLibraries | null; reload: () => void } => {
  const { value, reload } = useShared();
  return { installed: value, reload };
};
