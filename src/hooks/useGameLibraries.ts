import { useCallback, useEffect, useState } from "react";
import { GameLibraryChoice, LibrarySlot, userLibraryChoose, userLibraryGameChoice } from "../api";
import { ApplyConfirmation, changedChoice, gameApplyConfirmation, gameLibraryPickers } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";
import { useUserLibraries } from "./useUserLibraries";

/** A game's own choice of libraries on its page. A pick the patched game doesn't have yet asks to patch it again
 *  there and then (`onPatchAgain`); `patchedAs` changes when the game is patched, which may settle what it has. */
export const useGameLibraries = (
  appid: string | null,
  game: string,
  takesLibraries: boolean,
  patchedAs: unknown,
  onPatchAgain: () => void,
) => {
  const { installed } = useUserLibraries();
  const [choice, setChoice] = useState<GameLibraryChoice | null>(null);
  const [asking, setAsking] = useState<ApplyConfirmation | null>(null);

  const load = useCallback(() => {
    if (!appid) return;
    void safeAsyncOperation(() => userLibraryGameChoice(appid), "GameLibraries -> choice").then((answer) => setChoice(answer ?? null));
  }, [appid]);

  useEffect(load, [load, patchedAs]);

  const onChoose = async (slot: LibrarySlot, picked: string) => {
    if (!appid) return;
    const answer = await safeAsyncOperation(() => userLibraryChoose(appid, slot, changedChoice(picked)), "GameLibraries -> choose");
    setAsking(gameApplyConfirmation(game, answer?.to_apply));
    load();
  };

  return {
    view: gameLibraryPickers(installed, choice, takesLibraries),
    onChoose: (slot: LibrarySlot, picked: string) => void onChoose(slot, picked),
    confirmation: asking,
    onConfirm: () => {
      setAsking(null);
      onPatchAgain();
    },
    onCancel: () => setAsking(null),
  };
};
