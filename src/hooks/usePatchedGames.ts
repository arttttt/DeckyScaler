import { useCallback, useEffect, useState } from "react";
import { PatchedGames, patchedGames } from "../api";
import { gamesPageView } from "../presentation/games";
import { useInstalledLibrary } from "./useInstalledLibrary";

/** Every game the plugin patched, read when the page opens and again after a row changes one. */
export const usePatchedGames = () => {
  const { library } = useInstalledLibrary();
  const [answer, setAnswer] = useState<PatchedGames | null>(null);

  const reload = useCallback(async () => {
    try {
      setAnswer(await patchedGames());
    } catch (err) {
      setAnswer({ status: "error", message: err instanceof Error ? err.message : "Couldn't list the patched games." });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { view: gamesPageView(answer, library), reload };
};
