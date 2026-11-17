import { useCallback, useEffect, useState } from "react";
import { InstalledProton, ProtonMove, protonGames, protonInstalled, protonKeep, protonMoved } from "../api";
import { installedWithSteamNames, restartSteam, specifyCompatTool } from "../api/steamClient";
import { MOVE_CONFIRM_MS, MOVE_POLL_MS, MoveState, moveOutcome, protonPageView, unconfirmed } from "../presentation/proton";
import { safeAsyncOperation } from "../utils";

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

/** State and calls behind the Proton page; `reload` after its dialogs change the builds. */
export const useProtonPage = () => {
  const [installed, setInstalled] = useState<InstalledProton | null>(null);
  const [move, setMove] = useState<MoveState>(null);

  const reload = useCallback(() => {
    void safeAsyncOperation(() => protonInstalled(), "ProtonPage -> protonInstalled").then((answer) => {
      if (answer) setInstalled(installedWithSteamNames(answer));
    });
  }, []);

  useEffect(reload, [reload]);

  /** Moves the games through Steam, then waits for Steam's config to show them on the new build: Steam writes it
   *  after the call returns. Only the games it confirms are offered no more; the rest can be moved again. */
  const onMove = async (offer: ProtonMove) => {
    setMove({ target: offer.target, busy: true, message: null });
    const appids = offer.games.map((game) => game.appid);
    appids.forEach((appid) => specifyCompatTool(Number(appid), offer.target));
    let pending = appids;
    for (const deadline = Date.now() + MOVE_CONFIRM_MS; pending.length > 0 && Date.now() < deadline; ) {
      await wait(MOVE_POLL_MS);
      const now = await safeAsyncOperation(() => protonGames(offer.target), "ProtonPage -> protonGames");
      if (now?.status === "success") pending = unconfirmed(appids, now.games);
    }
    const confirmed = appids.filter((appid) => !pending.includes(appid));
    if (confirmed.length > 0) await safeAsyncOperation(() => protonMoved(offer.target, confirmed), "ProtonPage -> protonMoved");
    setMove({ target: offer.target, busy: false, message: moveOutcome(offer, pending) });
    reload();
  };

  const onKeep = async (offer: ProtonMove) => {
    await safeAsyncOperation(() => protonKeep(offer.target), "ProtonPage -> protonKeep");
    reload();
  };

  return {
    view: protonPageView(installed, move),
    reload,
    onRestart: restartSteam,
    onMove: (offer: ProtonMove) => void onMove(offer),
    onKeep: (offer: ProtonMove) => void onKeep(offer),
  };
};
