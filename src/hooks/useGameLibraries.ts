import { useCallback, useEffect, useState } from "react";
import { GameLibraryChoice, LibrarySlot, userLibraryChoose, userLibraryGameChoice } from "../api";
import { changedChoice, gameLibraryPickers } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";
import { useUserLibraries } from "./useUserLibraries";

/** A game's own choice of libraries on its page. `patchedAs` changes when the game is patched again, which may
 *  settle what the game has. */
export const useGameLibraries = (appid: string | null, takesLibraries: boolean, patchedAs: unknown) => {
  const { installed } = useUserLibraries();
  const [choice, setChoice] = useState<GameLibraryChoice | null>(null);

  const load = useCallback(() => {
    if (!appid) return;
    void safeAsyncOperation(() => userLibraryGameChoice(appid), "GameLibraries -> choice").then((answer) => setChoice(answer ?? null));
  }, [appid]);

  useEffect(load, [load, patchedAs]);

  const onChoose = async (slot: LibrarySlot, picked: string) => {
    if (!appid) return;
    await safeAsyncOperation(() => userLibraryChoose(appid, slot, changedChoice(picked)), "GameLibraries -> choose");
    load();
  };

  return {
    view: gameLibraryPickers(installed, choice, takesLibraries),
    onChoose: (slot: LibrarySlot, picked: string) => void onChoose(slot, picked),
  };
};
